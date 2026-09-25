from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId

from app.agents.telemetry_agent import _signal_changed
from app.core.settings import settings
from app.models.telemetry import RankingSignal
from app.services.audience_forecast import forecast_leads


def candidate(lead_id: str = "forecast-lead") -> dict:
    return {
        "lead_id": lead_id,
        "headline": "Ohio technology investment creates new regional jobs",
        "topic": "technology",
        "geo": "Ohio",
        "base_score": 0.7,
        "trend_score": {"trend_strength": 0.8},
    }


def test_telemetry_sample_growth_triggers_forecast_refresh():
    previous = {"weight_delta": 0.04, "sample_size": 10, "confidence": 0.6}
    current = RankingSignal(
        topic_geo_key="technology|Ohio",
        topic="technology",
        geo="Ohio",
        weight_delta=0.04,
        sample_size=11,
        confidence=0.6,
        last_updated=datetime.now(UTC),
    )
    assert _signal_changed(previous, current)


async def insert_outcomes(db, count: int, now: datetime) -> None:
    for index in range(count):
        article_id = ObjectId()
        published_at = now - timedelta(days=10 + index)
        await db.articles.insert_one(
            {
                "_id": article_id,
                "title": f"Technology outcome {index}",
                "topic": "technology",
                "geo": "Ohio",
                "status": "published",
                "published_at": published_at,
            }
        )
        await db.article_daily_metrics.insert_one(
            {
                "article_id": article_id,
                "day": (published_at + timedelta(days=1)).date().isoformat(),
                "views": 1_000 + index * 250,
            }
        )


@pytest.mark.asyncio
async def test_forecast_withholds_reader_number_until_outcomes_exist(db):
    await db.ranking_signals.insert_one(
        {
            "_id": "technology|Ohio",
            "weight_delta": 0.08,
            "sample_size": 120,
            "confidence": 0.8,
        }
    )
    result = (await forecast_leads([candidate()]))["forecast-lead"]
    assert result.status == "insufficient_data"
    assert result.predicted_readers is None
    assert result.audience_demand == "high"
    assert result.telemetry_sample_size == 120


@pytest.mark.asyncio
async def test_forecast_uses_completed_seven_day_historical_outcomes(db, monkeypatch):
    now = datetime.now(UTC)
    monkeypatch.setattr(settings, "audience_forecast_min_baseline_stories", 3)
    monkeypatch.setattr(settings, "audience_forecast_min_model_stories", 30)
    await insert_outcomes(db, 3, now)
    await db.ranking_signals.insert_one(
        {"_id": "technology|Ohio", "weight_delta": 0.02, "sample_size": 50, "confidence": 0.7}
    )
    result = (await forecast_leads([candidate()], now))["forecast-lead"]
    assert result.status == "historical_baseline"
    assert result.predicted_readers is not None
    assert result.lower_bound <= result.predicted_readers <= result.upper_bound
    assert result.comparable_stories == 3
    assert any("Historical baseline" in factor for factor in result.factors)


@pytest.mark.asyncio
async def test_forecast_advances_to_calibrated_statistical_model(db, monkeypatch):
    now = datetime.now(UTC)
    monkeypatch.setattr(settings, "audience_forecast_min_baseline_stories", 3)
    monkeypatch.setattr(settings, "audience_forecast_min_model_stories", 5)
    await insert_outcomes(db, 5, now)
    await db.ranking_signals.insert_one(
        {"_id": "technology|Ohio", "weight_delta": 0.03, "sample_size": 150, "confidence": 0.8}
    )
    result = (await forecast_leads([candidate()], now))["forecast-lead"]
    assert result.status == "calibrated_model"
    assert result.predicted_readers is not None
    assert result.model_version == "audience_forecast_v1"
    assert any("ridge model" in factor for factor in result.factors)
