"""Auditable seven-day audience forecasting with data-maturity fallbacks."""

from __future__ import annotations

import hashlib
import math
import statistics
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.database import get_database
from app.core.settings import settings
from app.models.agents import AudienceForecast

MODEL_VERSION = "audience_forecast_v1"
TOPICS = ("nation-world", "business", "technology", "climate", "health", "science", "local", "sports", "culture")
BROAD_GEOS = {"", "global", "national", "us", "usa", "united states"}
GEO_BUCKETS = 8


def _median(values: list[int]) -> float:
    return float(statistics.median(values)) if values else 0.0


def _round_readers(value: float) -> int:
    value = max(0.0, value)
    step = 10 if value < 1_000 else 100 if value < 10_000 else 1_000
    return int(round(value / step) * step)


def _features(item: dict[str, Any], when: datetime) -> list[float]:
    topic = str(item.get("topic", "general")).casefold()
    geo = str(item.get("geo", "global")).strip().casefold()
    headline_words = min(30, len(str(item.get("headline", item.get("title", ""))).split())) / 30
    weekday_angle = 2 * math.pi * when.weekday() / 7
    geo_bucket = hashlib.sha256(geo.encode()).digest()[0] % GEO_BUCKETS
    return [
        1.0,
        headline_words,
        0.0 if geo in BROAD_GEOS else 1.0,
        math.sin(weekday_angle),
        math.cos(weekday_angle),
        *(1.0 if topic == known else 0.0 for known in TOPICS),
        *(1.0 if geo_bucket == known else 0.0 for known in range(GEO_BUCKETS)),
    ]


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float] | None:
    """Small Gaussian-elimination solver used to avoid a heavyweight ML dependency."""
    size = len(vector)
    augmented = [matrix[row][:] + [vector[row]] for row in range(size)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-9:
            return None
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                current - factor * source
                for current, source in zip(augmented[row], augmented[column], strict=True)
            ]
    return [augmented[row][-1] for row in range(size)]


def _fit_ridge(outcomes: list[dict[str, Any]]) -> tuple[list[float], float] | None:
    rows = [_features(item, item["published_at"]) for item in outcomes]
    targets = [math.log1p(item["views_7d"]) for item in outcomes]
    width = len(rows[0])
    matrix = [[0.0] * width for _ in range(width)]
    vector = [0.0] * width
    for row, target in zip(rows, targets, strict=True):
        for left in range(width):
            vector[left] += row[left] * target
            for right in range(width):
                matrix[left][right] += row[left] * row[right]
    for index in range(1, width):
        matrix[index][index] += 1.0
    coefficients = _solve(matrix, vector)
    if coefficients is None:
        return None
    residuals = [
        target - sum(value * coefficient for value, coefficient in zip(row, coefficients, strict=True))
        for row, target in zip(rows, targets, strict=True)
    ]
    residual_std = statistics.pstdev(residuals) if len(residuals) > 1 else 0.5
    return coefficients, max(0.15, residual_std)


async def _completed_outcomes(now: datetime) -> list[dict[str, Any]]:
    cutoff = now - timedelta(days=7)
    cursor = (
        get_database()
        .articles.find(
            {"status": "published", "published_at": {"$lte": cutoff}},
            {"title": 1, "topic": 1, "geo": 1, "published_at": 1},
        )
        .sort("published_at", -1)
        .limit(2_000)
    )
    articles = [
        article
        async for article in cursor
    ]
    if not articles:
        return []
    ids = [article["_id"] for article in articles]
    daily = [
        document
        async for document in get_database().article_daily_metrics.find({"article_id": {"$in": ids}})
    ]
    by_article: dict[Any, list[dict[str, Any]]] = {}
    for document in daily:
        by_article.setdefault(document["article_id"], []).append(document)
    outcomes: list[dict[str, Any]] = []
    for article in articles:
        rows = by_article.get(article["_id"], [])
        if not rows:
            continue  # Pre-instrumentation stories are not valid zero-view outcomes.
        published_day = article["published_at"].date()
        views = sum(
            int(row.get("views", 0))
            for row in rows
            if 0 <= (datetime.fromisoformat(row["day"]).date() - published_day).days < 7
        )
        outcomes.append({**article, "views_7d": views})
    return outcomes


async def forecast_leads(candidates: list[dict[str, Any]], now: datetime | None = None) -> dict[str, AudienceForecast]:
    forecast_now = now or datetime.now(UTC)
    outcomes = await _completed_outcomes(forecast_now)
    signals = {
        str(item["_id"]): item
        async for item in get_database().ranking_signals.find(
            {}, {"weight_delta": 1, "sample_size": 1, "confidence": 1}
        )
    }
    trained = _fit_ridge(outcomes) if len(outcomes) >= settings.audience_forecast_min_model_stories else None
    all_views = [int(item["views_7d"]) for item in outcomes]
    global_median = _median(all_views)
    forecasts: dict[str, AudienceForecast] = {}
    completed_stories = len(outcomes)
    next_stage_target = (
        settings.audience_forecast_min_baseline_stories
        if completed_stories < settings.audience_forecast_min_baseline_stories
        else settings.audience_forecast_min_model_stories
        if completed_stories < settings.audience_forecast_min_model_stories
        else None
    )

    for candidate in candidates:
        topic = str(candidate.get("topic", "general"))
        geo = str(candidate.get("geo", "global"))
        signal = signals.get(f"{topic}|{geo}", signals.get(f"{topic}|global", {}))
        telemetry_delta = float(signal.get("weight_delta", 0.0) or 0.0)
        telemetry_sample = int(signal.get("sample_size", 0) or 0)
        signal_confidence = float(signal.get("confidence", 0.0) or 0.0)
        sample_reliability = min(1.0, math.sqrt(telemetry_sample / 100)) if telemetry_sample else 0.0
        trusted_delta = telemetry_delta * sample_reliability * signal_confidence
        trend_strength = float((candidate.get("trend_score") or {}).get("trend_strength", 0.0) or 0.0)
        cap = max(0.01, settings.agent_max_weight_delta)
        demand_score = min(
            1.0,
            max(
                0.0,
                0.55 * (0.5 + trusted_delta / (2 * cap))
                + 0.30 * trend_strength
                + 0.15 * float(candidate.get("base_score", 0.5)),
            ),
        )
        demand = "high" if demand_score >= 0.67 else "low" if demand_score < 0.4 else "moderate"
        comparable = [
            item
            for item in outcomes
            if item.get("topic") == topic or (geo.casefold() not in BROAD_GEOS and item.get("geo") == geo)
        ]
        factors = [
            f"Audience demand is {demand} from a {telemetry_sample}-reader telemetry sample.",
            f"Current topic/geography ranking adjustment is {telemetry_delta:+.2f} "
            f"at {signal_confidence:.0%} signal confidence.",
        ]
        if len(outcomes) < settings.audience_forecast_min_baseline_stories or not comparable:
            forecasts[candidate["lead_id"]] = AudienceForecast(
                status="insufficient_data",
                confidence="low",
                audience_demand=demand,
                comparable_stories=len(comparable),
                telemetry_sample_size=telemetry_sample,
                completed_stories=completed_stories,
                next_stage_target=next_stage_target,
                model_version=MODEL_VERSION,
                factors=factors + ["More completed seven-day story outcomes are required for a readership forecast."],
            )
            continue

        if trained is not None:
            coefficients, residual_std = trained
            row = _features(candidate, forecast_now)
            log_prediction = sum(value * coefficient for value, coefficient in zip(row, coefficients, strict=True))
            raw_prediction = max(0.0, math.expm1(log_prediction))
            lower = max(0.0, math.expm1(log_prediction - 1.28 * residual_std))
            upper = math.expm1(log_prediction + 1.28 * residual_std)
            status = "calibrated_model"
            factors.append(f"Calibrated ridge model trained on {len(outcomes)} completed stories.")
        else:
            topic_views = [int(item["views_7d"]) for item in outcomes if item.get("topic") == topic]
            geo_views = [int(item["views_7d"]) for item in outcomes if item.get("geo") == geo]
            pieces = [(global_median, 0.2)]
            if topic_views:
                pieces.append((_median(topic_views), 0.55))
            if geo.casefold() not in BROAD_GEOS and geo_views:
                pieces.append((_median(geo_views), 0.25))
            raw_prediction = sum(value * weight for value, weight in pieces) / sum(weight for _, weight in pieces)
            comparable_views = [int(item["views_7d"]) for item in comparable]
            if len(comparable_views) >= 2:
                percentiles = statistics.quantiles(comparable_views, n=5, method="inclusive")
                lower, upper = percentiles[0], percentiles[-1]
            else:
                lower, upper = raw_prediction * 0.6, raw_prediction * 1.4
            status = "historical_baseline"
            factors.append(f"Historical baseline uses {len(comparable)} comparable topic or geography stories.")

        momentum = min(1.3, max(0.7, 1 + trusted_delta * 2 + trend_strength * 0.15))
        raw_prediction *= momentum
        lower *= momentum
        upper *= momentum
        if settings.audience_subscriber_count > 0:
            subscriber_readers = settings.audience_subscriber_count * settings.audience_subscriber_view_rate
            raw_prediction = raw_prediction * 0.75 + subscriber_readers * 0.25
            lower = lower * 0.75 + subscriber_readers * 0.20
            upper = upper * 0.75 + subscriber_readers * 0.30
            factors.append(
                f"Subscriber reach uses {settings.audience_subscriber_count:,} subscribers at the configured "
                f"{settings.audience_subscriber_view_rate:.0%} view rate."
            )
        if telemetry_sample < 25:
            confidence = "low"
            uncertainty_scale = 1.25
        elif status == "calibrated_model" and len(outcomes) >= 50 and telemetry_sample >= 100:
            confidence = "high"
            uncertainty_scale = 0.9
        else:
            confidence = "medium"
            uncertainty_scale = 1.0
        midpoint = (lower + upper) / 2
        half_range = (upper - lower) / 2 * uncertainty_scale
        lower = max(0.0, midpoint - half_range)
        upper = midpoint + half_range
        factors.append(
            f"Forecast confidence accounts for {len(outcomes)} completed outcomes and "
            f"a {telemetry_sample}-reader telemetry sample."
        )
        forecasts[candidate["lead_id"]] = AudienceForecast(
            status=status,
            predicted_readers=_round_readers(raw_prediction),
            lower_bound=_round_readers(lower),
            upper_bound=max(_round_readers(lower), _round_readers(upper)),
            confidence=confidence,
            audience_demand=demand,
            comparable_stories=len(comparable),
            telemetry_sample_size=telemetry_sample,
            completed_stories=completed_stories,
            next_stage_target=next_stage_target,
            model_version=MODEL_VERSION,
            factors=factors,
        )
    return forecasts
