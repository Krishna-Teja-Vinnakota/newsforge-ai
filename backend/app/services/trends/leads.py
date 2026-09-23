"""Turn strong, under-covered cached trend signals into pending leads."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from app.core.database import get_database
from app.core.settings import settings
from app.models.trends import TrendSignal
from app.services.articles import load_recent_published_article_metadata
from app.services.trends.refresh import load_fresh_signals
from app.services.trends.scoring import SATURATION_STORIES, count_recent_coverage, topic_strength

logger = logging.getLogger("newsforge.trends.leads")

ORIGIN_TREND_FEED = "trend_feed"
DECIDED_STATUSES = {"approved", "rejected"}


def _lead_id(topic_id: str, geo: str) -> str:
    return f"trend:{topic_id}:{(geo or 'global').strip().lower()}"


def _group_signals(signals: list[TrendSignal]) -> dict[tuple[str, str], list[TrendSignal]]:
    """Group by (topic_id, geo). Signals for the same story from different sources with a
    different topic_id are not merged in v1 — that needs fuzzy label matching like the
    lead-to-signal matcher, which is deferred until we see how often it matters in practice."""
    groups: dict[tuple[str, str], list[TrendSignal]] = defaultdict(list)
    for signal in signals:
        groups[(signal.topic_id, signal.geo)].append(signal)
    return groups


async def promote_trend_leads(now: datetime | None = None) -> list[str]:
    """Create or refresh pending leads for topics trending above the configured threshold.

    Safety rules:
    - Off unless TRENDS_LEAD_INTAKE_ENABLED is true.
    - Never touches a lead an editor already approved or rejected.
    - Never touches a lead this step did not create (origin != "trend_feed").
    - Bounded per run by TRENDS_LEAD_MAX_PER_REFRESH.
    """
    if not settings.trends_lead_intake_enabled:
        return []
    scoring_now = now or datetime.now(UTC)
    signals = await load_fresh_signals(scoring_now, settings.trends_max_age_hours)
    if not signals:
        return []
    articles = await load_recent_published_article_metadata(now=scoring_now)

    candidates: list[dict[str, Any]] = []
    for (topic_id, geo), group in _group_signals(signals).items():
        scored = topic_strength(group, 0, now=scoring_now, max_signal_age_hours=settings.trends_max_age_hours)
        if not scored["trend_evidence"] or scored["trend_strength"] < settings.trends_lead_min_strength:
            continue
        best = scored["trend_evidence"][0]
        stories = count_recent_coverage({"headline": best["label"], "source_context": ""}, articles)
        if stories >= SATURATION_STORIES:
            continue  # already well covered; nothing new for an editor to weigh
        candidates.append(
            {
                "topic_id": topic_id,
                "geo": geo,
                "strength": scored["trend_strength"],
                "best": best,
                "evidence": scored["trend_evidence"][:5],
                "stories_published_7d": stories,
            }
        )

    candidates.sort(key=lambda item: -item["strength"])
    candidates = candidates[: max(0, settings.trends_lead_max_per_refresh)]

    promoted: list[str] = []
    collection = get_database().lead_inbox
    for candidate in candidates:
        lead_id = _lead_id(candidate["topic_id"], candidate["geo"])
        existing = await collection.find_one({"lead_id": lead_id}, {"status": 1, "origin": 1})
        if existing and (existing.get("origin") != ORIGIN_TREND_FEED or existing.get("status") in DECIDED_STATUSES):
            continue
        best = candidate["best"]
        sources = sorted({item["source"] for item in candidate["evidence"]})
        context = (
            f"Trending on {', '.join(sources)} (strength {candidate['strength']:.2f} of 1.00); "
            f"{candidate['stories_published_7d']} related {'story' if candidate['stories_published_7d'] == 1 else 'stories'} "
            "published in the last 7 days."
        )
        await collection.update_one(
            {"lead_id": lead_id},
            {
                "$set": {
                    "headline": str(best["label"])[:180],
                    "topic": "trending",
                    "geo": candidate["geo"],
                    "source_url": best.get("source_url"),
                    "source_context": context,
                    "origin": ORIGIN_TREND_FEED,
                    "origin_evidence": candidate["evidence"],
                    "updated_at": scoring_now,
                },
                "$setOnInsert": {"lead_id": lead_id, "status": "pending", "created_at": scoring_now},
            },
            upsert=True,
        )
        promoted.append(lead_id)
    if promoted:
        logger.info("Promoted %s trend-sourced lead(s)", len(promoted))
    return promoted
