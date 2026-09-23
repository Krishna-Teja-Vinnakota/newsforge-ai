# Trend signals in the selection agent — implementation plan

Status: **implemented; post-review fixes applied (ambiguous geo codes, stricter matching).** Source of the idea: the `recommendation-agent` proof of concept (external trend connectors, coverage-gap scoring), adapted to NewsForge's async FastAPI + MongoDB backend.

## 1. Goal and principles

Add two audited score terms, `trend_boost` and `coverage_adjustment`, to lead ranking in `backend/app/agents/selection_agent.py`. Ingestion and scoring are controlled by separate flags, both off by default.

```
final_score = base_score + learned_weight_delta + trend_boost + coverage_adjustment
```

Principles:

- The LLM never affects scores. It only writes guidance text from supplied evidence.
- Ranking never makes outbound requests. It reads only the cached `trend_signals` collection.
- The same lead, matched against the same stored signals and coverage data, gets the same adjustment regardless of batch composition (no batch-relative normalisation).
- The audit is self-contained, so a decision can be reconstructed after signals expire.
- External text is treated as data wherever it reaches a prompt.

## 2. Flag states

| `TRENDS_REFRESH_ENABLED` | `TRENDS_SCORING_ENABLED` | Behaviour |
|---|---|---|
| off | off | Existing system unchanged (default) |
| on | off | **Shadow mode**: collect signals; record hypothetical `shadow_*` scores in the audit without changing `final_score` |
| on | on | Full feature |
| off | on | Uses only remaining unexpired cached signals |

- The background refresh loop starts only when `TRENDS_REFRESH_ENABLED=true`, regardless of the scoring flag.
- "Flag-off identical" means identical ordering and legacy score fields. Shadow mode adds `shadow_*` audit fields, so the whole serialized document is not byte-identical. Tests assert on ordering and legacy fields, not document equality.

## 3. Configuration

Add to `backend/app/core/settings.py`, `.env.example`, and the backend `environment:` block in `docker-compose.yml` (without the Compose change the values never reach the container).

```
TRENDS_REFRESH_ENABLED=false
TRENDS_SCORING_ENABLED=false
TRENDS_REFRESH_MINUTES=30
TRENDS_MAX_TOTAL_ADJUSTMENT=0.10
TRENDS_MAX_AGE_HOURS=6
TRENDS_GEO=US
TRENDS_SOURCES=google_news,weather,government,wikipedia
TRENDS_CONNECTOR_TIMEOUT_SECONDS=5
TRENDS_MAX_SIGNALS_PER_SOURCE=50
```

Credentials, if any source needs them, go in `.env` only.

## 4. Data model

```python
class TrendSignal(BaseModel):
    topic_id: str
    label: str
    source: str
    geo: str                      # "global", a country code, or a local area
    country_code: str | None      # resolved country, if known
    interest_score: float
    velocity: float
    rank: int | None
    observed_at: datetime
    fetched_at: datetime
    expires_at: datetime          # per-connector lifetime (alerts short, Wikipedia longer)
    source_url: str | None
    raw: dict[str, Any]
```

- Collection `trend_signals`, keyed `topic_id|source|geo`, with a TTL index on `expires_at`.
- Every scoring query also filters `expires_at > now`. TTL deletion is lazy and mongomock does not model it faithfully.
- Collection `trend_refresh_runs` stores refresh history so status survives restarts.

### Geography matching (v1)

Lead `geo` is a free-form string (seed data has `Ohio`, `global`, `national`, `baseline`), so hierarchy needs a deterministic rule:

1. `global` signals apply everywhere.
2. Exact normalized geo matches apply.
3. A country signal applies to a local lead only when `resolve_country(lead.geo)` succeeds (static lookup of US states and major cities, country names and codes). `national` resolves to `TRENDS_GEO`.
4. Unknown geographies (for example `baseline`) resolve to `None` and get no country-level boost.
   Codes that are both a US state and a country code (`CA`, `IN`, `DE`) are ambiguous: they resolve to `None`, including in `City, CA` forms, and never match by string equality either. Unambiguous spellings (`California`, `Canada`, `Indiana`, `India`) still resolve.
5. A local signal never affects unrelated geographies.

## 5. Scoring (`scoring_version = "selection_v2_trends_2"`)

Any constant change bumps the version string.

```
per-signal:
  raw       = interest × velocity_multiplier + rank_bonus + official_bonus + severity_bonus
  freshness = max(0, 1 − age / lifetime)            # age measured from observed_at
  effective = raw × freshness

external_raw   = max(effective) over geo-eligible matched signals   # duplicates do not stack
trend_strength = t = clamp(external_raw / 150, 0, 1)                # fixed scale, not batch-relative

saturation = s = min(stories_published_7d / 10, 1)

trend_boost         = t × M
coverage_adjustment = t × M × (1 − 2s)
M                   = TRENDS_MAX_TOTAL_ADJUSTMENT
```

- **Combined budget:** if `|trend_boost + coverage_adjustment| > M`, scale both terms down proportionally so the total never exceeds `M`.
- **Velocity:** rescaled against the median of its own source (computed over stored signals for that source, not over the leads being ranked), bounded 0.5–2.0×.
- **Coverage:** count published articles with `published_at >= now − 7 days`, matched against title, dek, tags and topic (not body) using the same token logic as lead matching.
- **Matching rule (v2 scoring):** a lead matches a trend label or article only when they share at least 2 significant tokens (`MIN_SHARED_TOKENS`) and the overlap ratio is at least 0.6 of the smaller token set. Stopwords include newsroom and alert boilerplate (`warning`, `issued`, dates, time zones). The lead's broad `topic` is excluded from the match text, so category words cannot link unrelated stories. One-word trend labels therefore never match. Deduplicate articles. Load recent article metadata once per selection run (no per-lead queries). Confirm `articles` field names before coding.
- **Suggested format:** deterministic (`breaking` for red/amber alerts, top-ranked official signals or a large gap; otherwise `explainer`, `live-blog`, or `standard`).

### Saturation behaviour (documented v1 decision)

`combined = tM + tM(1 − 2s) = 2tM(1 − s)`, which is never negative:

- No coverage: maximum positive boost.
- Half saturated (5 stories): the ordinary trend boost remains.
- Fully saturated: the coverage adjustment cancels the trend boost.

Trends can promote an opportunity. Coverage saturation can remove that promotion but never penalises the underlying editorial score. Because of the combined-budget cap, a strongly trending topic (`t ≈ 1`) receives the same boost `M` for any coverage up to about five recent stories; coverage only differentiates once `s > 0.5`. For weaker trends the gradient applies across the whole range. This is intentional for v1. Shadow mode is how we decide whether to tune it, for example by giving each term its own share of the budget.

## 6. Audit shape

`score_audit` must be reconstructable after signals are deleted. It stores a full config snapshot, not just the version string.

```json
{
  "scoring_version": "selection_v2_trends_2",
  "base_score": 0.62, "learned_delta": 0.03,
  "trend_boost": 0.07, "coverage_adjustment": 0.02, "final_score": 0.74,
  "stories_published_7d": 1,
  "trend_config": {
    "strength_scale": 150,
    "max_total_adjustment": 0.10,
    "match_threshold": 0.6,
    "min_shared_tokens": 2,
    "match_text_fields": ["headline", "source_context"],
    "saturation_stories": 10,
    "velocity_multiplier_bounds": [0.5, 2.0],
    "bonus_constants": {"official": 18, "severity": {"red": 40, "amber": 25, "...": "..."}},
    "freshness_lifetimes_hours": {"weather_alert": 6, "wikipedia": 24, "...": "..."}
  },
  "trend_evidence": [{
    "signal_id": "topic|source|geo", "source": "weather_alert", "label": "…",
    "geo": "US", "country_code": "US",
    "interest_score": 82, "rank": 2, "velocity": 1.8,
    "source_median_velocity": 1.4, "velocity_multiplier": 1.29,
    "freshness_multiplier": 0.76, "rank_bonus": 38, "official_bonus": 18, "severity_bonus": 0,
    "effective_score": 122.4, "observed_at": "…", "expires_at": "…",
    "matched_tokens": ["heat", "warning"]
  }]
}
```

In shadow mode the same block is written with `shadow_trend_boost` and `shadow_coverage_adjustment`; `final_score` is unchanged.

## 7. Refresh semantics

Per `(source, geo)` scope:

| Outcome | Behaviour |
|---|---|
| `success` | Upsert returned signals and remove older signals for that scope that were absent from the response |
| `success_empty` | Clear the previous snapshot for that scope |
| `failed` (timeout, rate limit, parse or transport error) | Keep existing unexpired signals; never clear |

The upsert and the removal of absent signals happen as one operation so readers never see a half-replaced snapshot. Only a definite `success` or `success_empty` may delete anything.

## 8. Phases

### Phase 0 — Prerequisite refactor (own PR, no behaviour change)

- Extract one `persist_ranked_leads()` and one `lead_to_item()` mapper.
- The selection agent and the `/selection/run` route both use them. The route stops recomputing `final_score` (`backend/app/api/routes/agents.py`, near line 141), which would otherwise discard the new terms.
- Replace the hand-built `LeadInboxItem` in `list_leads`, `approve_lead` and `reject_lead` with the mapper.
- Add the score fields to `LeadInboxItem`.
- Done when existing tests pass unchanged.

### Phase 1 — Ingestion

- `backend/app/services/trends/` with async `httpx` connectors, in order: Google News RSS, weather alerts, government feeds, Wikipedia, GDELT (enrichment only), Reddit (off by default; must degrade cleanly).
- Per connector: timeout, response-size cap, `TRENDS_MAX_SIGNALS_PER_SOURCE` cap, retries only for 429/502/503 with bounded backoff.
- Refresh job: `asyncio.Lock` against overlap, bounded concurrency, initial refresh at startup, clean cancellation on shutdown, snapshot semantics from section 7.
- Triggers: background loop (only when `TRENDS_REFRESH_ENABLED=true`) and `POST /api/v1/agents/trends/refresh` (editor roles).
- `GET /api/v1/agents/trends/status` returns per-source `status`, `count`, `duration_ms`, `last_success_at`, `error_code`, and `next_refresh_at`. Safe error codes only; details are logged server-side.
- Both flags off: no loop, no outbound calls.

### Phase 2 — Scoring module

- `backend/app/services/trends/scoring.py`: pure functions for section 5, lead-to-signal matching (0.6 token overlap, stopwords, matched tokens returned for the audit), `resolve_country`, and geo eligibility.
- Recent-story counting support in `backend/app/services/articles.py`.
- Done when unit tests pass, including determinism across batch compositions.

### Phase 3 — Wire into selection

- `run_selection` loads fresh signals and recent articles once per run and computes the terms; results go through the shared persistence from Phase 0.
- Add `trend_boost`, `coverage_adjustment`, `trend_evidence`, `suggested_format` and an optional `why_now` to `RankedLead`, `LeadInboxItem` and the stored document.
- Add `why_now` to the guidance schema and bump the selection `PROMPT_VERSION`. Keep fields distinct: `reasoning` is the deterministic score explanation; `why_now` and `suggested_angle` are LLM-written; `suggested_format` is deterministic.
- Trend labels enter the prompt as quoted, length-capped data.
- Telemetry rerank must preserve the trend fields.
- Scoring flag off: identical ordering and legacy fields. Shadow mode: audit only.

### Phase 4 — Studio (small PR)

- Update the `RankedLead` and `AiLead` types.
- `ScoreInspectorDrawer.tsx` shows both new terms and matched sources.
- A "Trending" chip and a format badge in the lead views.

### Phase 5 — Lead intake from trends (implemented)

Turns strong, under-covered cached trend signals into new `pending` leads in `lead_inbox`, so editors see them in the normal inbox rather than needing a separate feed.

- **Off by default:** `TRENDS_LEAD_INTAKE_ENABLED=false`. It only has cached signals to work from once `TRENDS_REFRESH_ENABLED=true`.
- **New settings:** `TRENDS_LEAD_MIN_STRENGTH` (default 0.5, the same `trend_strength` used in scoring) and `TRENDS_LEAD_MAX_PER_REFRESH` (default 5), so one refresh cannot flood the inbox.
- **Grouping:** `backend/app/services/trends/leads.py` groups fresh signals by `(topic_id, geo)` and scores each group with `topic_strength()`, a topic-level sibling of `score_trend_adjustment` that shares its per-signal evidence calculation but has no lead headline to fuzzy-match against, since the signals are already grouped. Different sources that describe the same story under a different `topic_id` are **not merged** in v1 — that needs the same kind of fuzzy matching used for lead-to-signal matching, deferred until shadow data shows how often it matters.
- **Coverage check:** a group is skipped if `count_recent_coverage` already finds 10 or more matching published articles (the same `SATURATION_STORIES` threshold as scoring) — nothing new for an editor to weigh.
- **Lead identity:** `lead_id = "trend:<topic_id>:<geo>"`, so re-running promotion updates the same lead (headline, evidence, `source_context`) instead of duplicating it.
- **Never overwrites an editorial decision:** a lead is skipped if it already exists with `status` `approved` or `rejected`, or if it exists but was not created by this step (`origin != "trend_feed"`). A rejected trend lead stays rejected on every later run.
- **Fields written:** `headline` (the strongest matched signal's label), `topic: "trending"` (editors can retag), `geo`, `source_url`, a `source_context` summary naming the sources and story count, `origin: "trend_feed"`, and `origin_evidence` (up to 5 signals). `base_score` is left unset, so the normal editorial heuristic and, once scoring is on, `trend_boost` apply to it like any other lead — its headline is literally the trend label, so it matches strongly.
- **Triggers:** automatically at the end of every `refresh_trends()` run (scheduled or manual `POST /agents/trends/refresh`), and on demand via `POST /agents/trends/promote-leads`, which promotes from the existing cache without fetching. Both are editor-only. `TrendRefreshResponse.leads_promoted` lists the lead ids touched.
- **Studio:** a lead with `origin: "trend_feed"` shows a "From trends" badge in the inbox, alongside the existing Trending chip and format badge.

### Later (not in this pass)

Fuzzy-merging trend signals across sources for the same story, a dedicated "Suggested topics" review panel, Twitter/X or Databricks connectors, Tavily-based lead enrichment, and learning weights from outcomes.

## 9. Test plan

Scoring and matching:
- Geo mismatch gives zero boost; `Ohio` resolves to US; `baseline` gets no country-level boost.
- An expired signal gives zero boost even when TTL cleanup has not run.
- The same lead gets the same adjustment regardless of batch composition.
- Duplicate source rows do not stack.
- Combined-budget scaling is correct; saturation never yields a negative combined term.
- Freshness decays linearly from `observed_at`.

Ingestion:
- A failing source preserves its fresh signals; `success` removes absent signals; `success_empty` clears the scope; timeouts never clear.
- Scheduled and manual refreshes cannot overlap.
- `success_empty` is not reported as a failure.

Integration:
- Scoring off makes no outbound HTTP requests during selection.
- `GET /agents/leads` returns all audit fields.
- The selection API does not overwrite the agent's final score.
- Telemetry rerank preserves trend fields.
- Ties keep the current timestamp then ID ordering.
- Prompt-injection text in a trend label is treated as data.
- Shadow mode leaves ranks unchanged.

All HTTP is mocked; tests use no network.

## 10. Rollout

1. Merge Phase 0 (no behaviour change).
2. Merge Phases 1–3 with both flags off.
3. Enable refresh only (shadow mode) and compare `shadow_*` values against real editorial decisions.
4. Tune the strength scale, match threshold and budget split as needed, bumping `scoring_version` for each change.
5. Enable scoring.
6. Merge Phase 4.

## 11. Risks

| Risk | Mitigation |
|---|---|
| Rate limits or blocked sources | Cache, timeouts, isolated failures, status endpoint |
| False lead-to-trend matches | 0.6 threshold, stopwords, matched tokens in the audit, clamped effect |
| Cross-country boosts | Deterministic `resolve_country`; unknown geo gets none |
| Trends overriding editorial judgement | Combined budget plus shadow rollout |
| Stale data | Freshness decay, `expires_at` filter, snapshot replacement |
| Background loop in every replica | Acceptable with one backend container; add a Mongo lock if scaled out |
| Unofficial sources | Reddit off by default; `pytrends` excluded from v1 |

## 12. Decisions recorded

- Combined budget is scaled down proportionally when exceeded.
- `why_now` is optional on stored leads.
- `pytrends` is excluded from v1.
- Default geo is `US`, stored per signal and never hard-coded in scoring.
- Saturation removes a promotion but never penalises the editorial score (section 5).
