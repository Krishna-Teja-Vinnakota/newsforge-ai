from __future__ import annotations

import math
import re
import statistics
import unicodedata
from datetime import UTC, datetime
from typing import Any, Iterable

from app.models.trends import TrendSignal

SCORING_VERSION = "selection_v2_trends_2"
STRENGTH_SCALE = 150.0
MATCH_THRESHOLD = 0.6
# A single shared word is not a shared story: require at least this many shared
# significant tokens as well as the overlap ratio.
MIN_SHARED_TOKENS = 2
MATCH_TEXT_FIELDS = ("headline", "source_context")
SATURATION_STORIES = 10
VELOCITY_BOUNDS = (0.5, 2.0)
OFFICIAL_BONUS = 18.0
RANK_BONUS_MAX = 40.0
SEVERITY_BONUSES = {"red": 40.0, "amber": 25.0, "orange": 15.0, "yellow": 8.0}
FRESHNESS_LIFETIMES_HOURS = {
    "weather": 6,
    "weather_alert": 6,
    "google_news": 6,
    "government": 12,
    "wikipedia": 24,
    "gdelt": 6,
    "reddit": 6,
}

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "into",
    "is",
    "it",
    "its",
    "new",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "was",
    "were",
    "will",
    "with",
    "after",
    "amid",
    "over",
    "says",
    "say",
    "latest",
    "update",
    "updates",
}

# Function words plus newsroom and alert boilerplate, so two headlines do not match
# on shared scaffolding ("... warning issued until ... by NWS") instead of a shared subject.
STOPWORDS |= frozenset(
    """
    but her his how he we you your our they them then there these us uk
    against ahead among before between could during first get gets just like made make
    more most now off one other others out said see set some still than three two under
    until up via week weeks year years yesterday today tomorrow
    issued warning watch statement advisory special effect expires
    january february march april may june july august september october november december
    monday tuesday wednesday thursday friday saturday sunday
    sept am pm est edt cst cdt mst mdt pst pdt akdt hst utc gmt nws
    """.split()
)
# Dates and clock times ("16", "246am") are timestamps, not subject matter.
_NOISE_TOKEN = re.compile(r"^(?:\d{1,3}|\d+(?:am|pm))$")

US_STATES = {
    "alabama",
    "alaska",
    "arizona",
    "arkansas",
    "california",
    "colorado",
    "connecticut",
    "delaware",
    "florida",
    "georgia",
    "hawaii",
    "idaho",
    "illinois",
    "indiana",
    "iowa",
    "kansas",
    "kentucky",
    "louisiana",
    "maine",
    "maryland",
    "massachusetts",
    "michigan",
    "minnesota",
    "mississippi",
    "missouri",
    "montana",
    "nebraska",
    "nevada",
    "new hampshire",
    "new jersey",
    "new mexico",
    "new york",
    "north carolina",
    "north dakota",
    "ohio",
    "oklahoma",
    "oregon",
    "pennsylvania",
    "rhode island",
    "south carolina",
    "south dakota",
    "tennessee",
    "texas",
    "utah",
    "vermont",
    "virginia",
    "washington",
    "west virginia",
    "wisconsin",
    "wyoming",
    "district of columbia",
}
US_STATE_CODES = {
    "al",
    "ak",
    "az",
    "ar",
    "ca",
    "co",
    "ct",
    "de",
    "fl",
    "ga",
    "hi",
    "id",
    "il",
    "in",
    "ia",
    "ks",
    "ky",
    "la",
    "me",
    "md",
    "ma",
    "mi",
    "mn",
    "ms",
    "mo",
    "mt",
    "ne",
    "nv",
    "nh",
    "nj",
    "nm",
    "ny",
    "nc",
    "nd",
    "oh",
    "ok",
    "or",
    "pa",
    "ri",
    "sc",
    "sd",
    "tn",
    "tx",
    "ut",
    "vt",
    "va",
    "wa",
    "wv",
    "wi",
    "wy",
    "dc",
}
US_MAJOR_CITIES = {
    "new york city",
    "los angeles",
    "chicago",
    "houston",
    "phoenix",
    "philadelphia",
    "san antonio",
    "san diego",
    "dallas",
    "austin",
    "jacksonville",
    "fort worth",
    "columbus",
    "indianapolis",
    "charlotte",
    "seattle",
    "denver",
    "washington dc",
    "boston",
    "nashville",
    "detroit",
    "portland",
    "las vegas",
    "memphis",
    "louisville",
    "baltimore",
    "milwaukee",
    "albuquerque",
    "tucson",
    "fresno",
    "sacramento",
    "atlanta",
    "miami",
    "cleveland",
}
COUNTRY_ALIASES = {
    "us": "US",
    "usa": "US",
    "united states": "US",
    "united states of america": "US",
    "gb": "GB",
    "uk": "GB",
    "united kingdom": "GB",
    "great britain": "GB",
    "england": "GB",
    "in": "IN",
    "india": "IN",
    "ca": "CA",
    "canada": "CA",
    "au": "AU",
    "australia": "AU",
    "ie": "IE",
    "ireland": "IE",
    "de": "DE",
    "germany": "DE",
    "fr": "FR",
    "france": "FR",
    "jp": "JP",
    "japan": "JP",
    "cn": "CN",
    "china": "CN",
    "br": "BR",
    "brazil": "BR",
    "mx": "MX",
    "mexico": "MX",
    "za": "ZA",
    "south africa": "ZA",
    "nz": "NZ",
    "new zealand": "NZ",
}
MAJOR_CITY_COUNTRIES = {
    "london": "GB",
    "manchester": "GB",
    "birmingham": "GB",
    "edinburgh": "GB",
    "glasgow": "GB",
    "delhi": "IN",
    "new delhi": "IN",
    "mumbai": "IN",
    "bengaluru": "IN",
    "bangalore": "IN",
    "toronto": "CA",
    "vancouver": "CA",
    "montreal": "CA",
    "sydney": "AU",
    "melbourne": "AU",
    "dublin": "IE",
    "berlin": "DE",
    "paris": "FR",
    "tokyo": "JP",
    "beijing": "CN",
    "shanghai": "CN",
    "sao paulo": "BR",
    "mexico city": "MX",
    "auckland": "NZ",
}


AMBIGUOUS_GEO_CODES = frozenset(code for code in COUNTRY_ALIASES if len(code) == 2 and code in US_STATE_CODES)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def normalize_geo(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]+", " ", normalized).strip()


def tokenize(value: str | None) -> set[str]:
    normalized = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().casefold()
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalized)
        if len(token) > 1 and token not in STOPWORDS and not _NOISE_TOKEN.match(token)
    }


def matched_tokens(
    left: str, right: str, threshold: float = MATCH_THRESHOLD, min_shared: int = MIN_SHARED_TOKENS
) -> list[str]:
    left_tokens, right_tokens = tokenize(left), tokenize(right)
    if not left_tokens or not right_tokens:
        return []
    overlap = sorted(left_tokens & right_tokens)
    if len(overlap) < min_shared:
        return []
    return overlap if len(overlap) / min(len(left_tokens), len(right_tokens)) >= threshold else []


def resolve_country(geo: str | None, default_country: str = "US") -> str | None:
    normalized = normalize_geo(geo)
    if normalized == "national":
        return COUNTRY_ALIASES.get(normalize_geo(default_country), default_country.upper())
    if normalized in {"", "global", "baseline"}:
        return None
    # "CA", "IN" and "DE" are both a US state and a country code. A lead's geo does not say
    # which was meant, so it resolves to nothing rather than risking a cross-country boost.
    if normalized in AMBIGUOUS_GEO_CODES:
        return None
    if normalized in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[normalized]
    if normalized in US_STATES or normalized in US_STATE_CODES or normalized in US_MAJOR_CITIES:
        return "US"
    if normalized in MAJOR_CITY_COUNTRIES:
        return MAJOR_CITY_COUNTRIES[normalized]
    # Resolve common "City, Country" and "City, ST" forms without guessing unknown places.
    parts = normalized.split()
    if parts and parts[-1] in AMBIGUOUS_GEO_CODES:
        return None
    if parts and parts[-1] in US_STATE_CODES:
        return "US"
    if any(normalized.endswith(f" {state}") for state in US_STATES):
        return "US"
    for alias, code in COUNTRY_ALIASES.items():
        if normalized.endswith(f" {alias}"):
            return code
    return None


def geo_is_eligible(lead_geo: str, signal: TrendSignal, default_country: str = "US") -> bool:
    signal_geo = normalize_geo(signal.geo)
    lead_normalized = normalize_geo(lead_geo)
    if signal_geo == "global":
        return True
    # An ambiguous code (California vs Canada) never matches by string equality either.
    if lead_normalized in AMBIGUOUS_GEO_CODES:
        return False
    if signal_geo == lead_normalized:
        return True
    # Only a country-level signal fans out to local leads. A local signal may
    # carry its resolved country_code for auditing, but never crosses locality.
    if signal_geo not in COUNTRY_ALIASES:
        return False
    signal_country = COUNTRY_ALIASES[signal_geo]
    lead_country = resolve_country(lead_geo, default_country)
    return bool(signal_country and lead_country and signal_country.upper() == lead_country.upper())


def _lead_match_text(lead: dict[str, Any]) -> str:
    # The lead's broad `topic` (for example "nation-world") is deliberately excluded:
    # matching on a category word would link unrelated stories.
    return " ".join(str(lead.get(field) or "") for field in MATCH_TEXT_FIELDS)


def signal_matches_lead(lead: dict[str, Any], signal: TrendSignal) -> list[str]:
    return matched_tokens(_lead_match_text(lead), signal.label)


def article_matches_lead(lead: dict[str, Any], article: dict[str, Any]) -> bool:
    lead_text = _lead_match_text(lead)
    article_text = " ".join(
        [
            str(article.get("title") or ""),
            str(article.get("dek") or ""),
            str(article.get("topic") or ""),
            " ".join(str(tag) for tag in article.get("tags") or []),
        ]
    )
    return bool(matched_tokens(lead_text, article_text))


def count_recent_coverage(lead: dict[str, Any], articles: Iterable[dict[str, Any]]) -> int:
    seen: set[str] = set()
    for article in articles:
        identity = str(article.get("_id", article.get("id", "")))
        if identity not in seen and article_matches_lead(lead, article):
            seen.add(identity)
    return len(seen)


def source_velocity_medians(signals: Iterable[TrendSignal]) -> dict[str, float]:
    grouped: dict[str, list[float]] = {}
    for signal in signals:
        grouped.setdefault(signal.source, []).append(float(signal.velocity))
    return {source: float(statistics.median(values)) for source, values in grouped.items() if values}


def _velocity_multiplier(velocity: float, median: float) -> float:
    if median <= 0:
        return 1.0
    return max(VELOCITY_BOUNDS[0], min(VELOCITY_BOUNDS[1], velocity / median))


def trend_config_snapshot(
    max_total_adjustment: float, default_country: str = "US", max_signal_age_hours: int = 6
) -> dict[str, Any]:
    return {
        "strength_scale": STRENGTH_SCALE,
        "max_total_adjustment": max_total_adjustment,
        "max_signal_age_hours": max_signal_age_hours,
        "default_geo": default_country,
        "match_threshold": MATCH_THRESHOLD,
        "min_shared_tokens": MIN_SHARED_TOKENS,
        "match_text_fields": list(MATCH_TEXT_FIELDS),
        "saturation_stories": SATURATION_STORIES,
        "velocity_multiplier_bounds": list(VELOCITY_BOUNDS),
        "bonus_constants": {"rank_max": RANK_BONUS_MAX, "official": OFFICIAL_BONUS, "severity": SEVERITY_BONUSES},
        "freshness_lifetimes_hours": FRESHNESS_LIFETIMES_HOURS,
    }


def _freshness(signal: TrendSignal, now: datetime) -> float:
    observed = _utc(signal.observed_at)
    expires = _utc(signal.expires_at)
    if expires <= now:
        return 0.0
    configured = FRESHNESS_LIFETIMES_HOURS.get(signal.source, 6) * 3600
    declared = max(1.0, (expires - observed).total_seconds())
    lifetime = min(declared, configured)
    age = max(0.0, (now - observed).total_seconds())
    return max(0.0, 1.0 - age / lifetime)


def score_trend_adjustment(
    lead: dict[str, Any],
    signals: Iterable[TrendSignal],
    stories_published_7d: int,
    *,
    now: datetime | None = None,
    max_total_adjustment: float = 0.10,
    default_country: str = "US",
    max_signal_age_hours: int = 6,
) -> dict[str, Any]:
    """Return deterministic score terms and a self-contained evidence audit."""
    scoring_now = _utc(now or datetime.now(UTC))
    # The collection's key prevents duplicates, but deduplicate inputs here as well so
    # tests, migrations, or malformed caches cannot alter medians or stack evidence.
    unique: dict[str, TrendSignal] = {}
    for signal in signals:
        existing = unique.get(signal.signal_id)
        candidate_key = (_utc(signal.fetched_at), _utc(signal.observed_at), signal.interest_score, signal.velocity)
        existing_key = (
            (_utc(existing.fetched_at), _utc(existing.observed_at), existing.interest_score, existing.velocity)
            if existing
            else None
        )
        if existing_key is None or candidate_key > existing_key:
            unique[signal.signal_id] = signal
    signal_list = list(unique.values())
    medians = source_velocity_medians(signal_list)
    evidence: list[dict[str, Any]] = []
    effective_values: list[float] = []

    for signal in signal_list:
        signal_id = signal.signal_id
        if not geo_is_eligible(str(lead.get("geo", "global")), signal, default_country):
            continue
        tokens = signal_matches_lead(lead, signal)
        freshness = _freshness(signal, scoring_now)
        if not tokens or freshness <= 0:
            continue
        median = medians.get(signal.source, 1.0)
        velocity_multiplier = _velocity_multiplier(signal.velocity, median)
        rank_bonus = max(0.0, RANK_BONUS_MAX - float(signal.rank or RANK_BONUS_MAX)) if signal.rank else 0.0
        official_bonus = (
            OFFICIAL_BONUS
            if bool(signal.raw.get("official")) or signal.source in {"government", "weather", "weather_alert"}
            else 0.0
        )
        severity_bonus = SEVERITY_BONUSES.get(str(signal.raw.get("severity", "")).casefold(), 0.0)
        raw_score = signal.interest_score * velocity_multiplier + rank_bonus + official_bonus + severity_bonus
        effective = raw_score * freshness
        effective_values.append(effective)
        evidence.append(
            {
                "signal_id": signal_id,
                "source": signal.source,
                "label": signal.label,
                "geo": signal.geo,
                "country_code": signal.country_code,
                "interest_score": signal.interest_score,
                "rank": signal.rank,
                "velocity": signal.velocity,
                "source_median_velocity": round(median, 4),
                "velocity_multiplier": round(velocity_multiplier, 4),
                "freshness_multiplier": round(freshness, 4),
                "rank_bonus": round(rank_bonus, 4),
                "official_bonus": round(official_bonus, 4),
                "severity_bonus": round(severity_bonus, 4),
                "effective_score": round(effective, 4),
                "observed_at": signal.observed_at,
                "expires_at": signal.expires_at,
                "matched_tokens": tokens,
                "source_url": signal.source_url,
            }
        )

    evidence.sort(key=lambda item: (-item["effective_score"], item["signal_id"]))
    external_raw = max(effective_values, default=0.0)
    strength = max(0.0, min(1.0, external_raw / STRENGTH_SCALE))
    saturation = min(max(stories_published_7d, 0) / SATURATION_STORIES, 1.0)
    trend_boost = strength * max_total_adjustment
    coverage_adjustment = strength * max_total_adjustment * (1.0 - 2.0 * saturation)
    combined = trend_boost + coverage_adjustment
    if abs(combined) > max_total_adjustment and not math.isclose(combined, 0.0):
        scale = max_total_adjustment / abs(combined)
        trend_boost *= scale
        coverage_adjustment *= scale

    rounded_trend = round(trend_boost, 4)
    rounded_coverage = round(coverage_adjustment, 4)
    if abs(rounded_trend + rounded_coverage) > max_total_adjustment:
        bounded_total = math.copysign(max_total_adjustment, rounded_trend + rounded_coverage)
        rounded_coverage = round(bounded_total - rounded_trend, 4)
    return {
        "trend_boost": rounded_trend,
        "coverage_adjustment": rounded_coverage,
        "trend_strength": round(strength, 4),
        "stories_published_7d": stories_published_7d,
        "trend_evidence": evidence,
        "trend_config": trend_config_snapshot(max_total_adjustment, default_country, max_signal_age_hours),
    }


def suggested_format(score: dict[str, Any]) -> str:
    evidence = score.get("trend_evidence") or []
    # Severity lives in raw at ingestion; infer the audited bonus for the stored evidence.
    urgent = any(item.get("severity_bonus", 0) >= SEVERITY_BONUSES["amber"] for item in evidence)
    official_top = any(item.get("official_bonus", 0) > 0 and (item.get("rank") or 999) <= 3 for item in evidence)
    large_gap = score.get("trend_strength", 0) >= 0.8 and score.get("stories_published_7d", 0) <= 2
    if urgent or official_top or large_gap:
        return "breaking"
    if score.get("trend_strength", 0) >= 0.65 and score.get("stories_published_7d", 0) < 5:
        return "live-blog"
    if evidence:
        return "explainer"
    return "standard"
