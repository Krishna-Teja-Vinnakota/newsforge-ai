from datetime import UTC, datetime, timedelta

from app.models.trends import TrendSignal
from app.services.trends.scoring import (
    AMBIGUOUS_GEO_CODES,
    count_recent_coverage,
    geo_is_eligible,
    matched_tokens,
    resolve_country,
    score_trend_adjustment,
    signal_matches_lead,
)


NOW = datetime(2026, 9, 21, 12, tzinfo=UTC)


def signal(**updates) -> TrendSignal:
    values = {
        "topic_id": "heat-warning",
        "label": "Heat warning for Ohio",
        "source": "weather_alert",
        "geo": "US",
        "country_code": "US",
        "interest_score": 100,
        "velocity": 1.0,
        "rank": 1,
        "observed_at": NOW,
        "fetched_at": NOW,
        "expires_at": NOW + timedelta(hours=6),
        "source_url": "https://example.test/alert",
        "raw": {"official": True, "severity": "amber"},
    }
    values.update(updates)
    return TrendSignal(**values)


def lead(geo: str = "Ohio") -> dict:
    return {"headline": "Heat warning issued for Ohio", "topic": "climate", "geo": geo, "source_context": ""}


def test_geo_hierarchy_is_deterministic():
    assert resolve_country("Ohio") == "US"
    assert resolve_country("national", "GB") == "GB"
    assert resolve_country("baseline") is None
    assert geo_is_eligible("Ohio", signal())
    assert not geo_is_eligible("baseline", signal())
    assert not geo_is_eligible("London", signal())
    assert geo_is_eligible("London", signal(geo="global", country_code=None))
    assert not geo_is_eligible("Ohio", signal(geo="Cleveland", country_code="US"))


def test_expired_signals_are_ignored_without_ttl_cleanup():
    result = score_trend_adjustment(lead(), [signal(expires_at=NOW)], 0, now=NOW)
    assert result["trend_boost"] == 0
    assert result["coverage_adjustment"] == 0
    assert result["trend_evidence"] == []


def test_combined_budget_saturation_and_freshness():
    fresh = score_trend_adjustment(lead(), [signal()], 0, now=NOW, max_total_adjustment=0.10)
    saturated = score_trend_adjustment(lead(), [signal()], 10, now=NOW, max_total_adjustment=0.10)
    half_life = score_trend_adjustment(lead(), [signal()], 10, now=NOW + timedelta(hours=3))
    assert fresh["trend_boost"] + fresh["coverage_adjustment"] <= 0.10
    assert saturated["trend_boost"] + saturated["coverage_adjustment"] >= 0
    assert half_life["trend_evidence"][0]["freshness_multiplier"] == 0.5


def test_duplicate_rows_do_not_change_the_adjustment():
    one = score_trend_adjustment(lead(), [signal()], 2, now=NOW)
    duplicated = score_trend_adjustment(lead(), [signal(), signal()], 2, now=NOW)
    assert duplicated["trend_boost"] == one["trend_boost"]
    assert duplicated["coverage_adjustment"] == one["coverage_adjustment"]
    assert len(duplicated["trend_evidence"]) == 1


def test_coverage_matching_deduplicates_articles():
    article = {"_id": "story-1", "title": "Ohio heat warning issued", "dek": "", "topic": "climate", "tags": []}
    unrelated = {"_id": "story-2", "title": "Technology earnings", "dek": "", "topic": "business", "tags": []}
    assert count_recent_coverage(lead(), [article, article, unrelated]) == 1


def test_ambiguous_state_and_country_codes_resolve_to_nothing():
    assert {"ca", "in", "de"} <= AMBIGUOUS_GEO_CODES
    for code in ("CA", "IN", "DE", "Sacramento, CA"):
        assert resolve_country(code) is None
    # Unambiguous spellings still resolve.
    assert resolve_country("California") == "US"
    assert resolve_country("Canada") == "CA"
    assert resolve_country("Indiana") == "US"
    assert resolve_country("India") == "IN"
    assert resolve_country("OH") == "US"


def test_ambiguous_codes_never_receive_country_or_exact_matches():
    canada = signal(geo="CA", country_code="CA")
    united_states = signal(geo="US", country_code="US")
    assert not geo_is_eligible("CA", canada)  # would be an exact string match
    assert not geo_is_eligible("CA", united_states)
    assert not geo_is_eligible("IN", signal(geo="IN", country_code="IN"))
    assert geo_is_eligible("CA", signal(geo="global", country_code=None))
    assert geo_is_eligible("Canada", canada)


def test_a_single_shared_word_is_not_a_match():
    one_word = signal(label="Ohio")
    assert signal_matches_lead(lead(), one_word) == []
    assert matched_tokens("Ohio budget vote", "Ohio") == []
    assert matched_tokens("Ohio transit budget", "Ohio transit") == ["ohio", "transit"]


def test_shared_alert_boilerplate_does_not_link_different_stories():
    flood = {"headline": "Flood warning issued for Ohio until 16", "topic": "climate", "geo": "Ohio", "source_context": ""}
    heat = signal(label="Heat warning for Ohio")
    assert signal_matches_lead(flood, heat) == []
    assert signal_matches_lead(lead(), heat) == ["heat", "ohio"]


def test_lead_topic_category_words_do_not_create_matches():
    story = {"headline": "Budget vote delayed", "topic": "nation-world", "geo": "global", "source_context": ""}
    assert signal_matches_lead(story, signal(label="Nation world")) == []


def test_same_lead_gets_same_adjustment_whatever_else_is_scored():
    target = signal()
    other = signal(topic_id="other", label="Unrelated markets rally", source="google_news", velocity=2.0)
    alone = score_trend_adjustment(lead(), [target], 1, now=NOW)
    # Scoring other leads against the same signals never changes this lead's result.
    score_trend_adjustment({"headline": "Markets rally", "topic": "business", "geo": "global"}, [target, other], 0, now=NOW)
    again = score_trend_adjustment(lead(), [target, other], 1, now=NOW)
    for field in ("trend_boost", "coverage_adjustment", "trend_strength"):
        assert alone[field] == again[field]
