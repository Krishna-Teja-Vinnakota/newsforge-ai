# Intelligent Newsroom — PoC Implementation Plan

*A hackathon build spec. Read this once end-to-end before writing code. The most important section is §5 (Integration Contracts) — agree on it in the first hour so everyone can build in parallel against mocks.*

**Assumptions:** team of 3–4, ~24–36 hours. If we're smaller, one person owns two adjacent workstreams (see §7). If we have more time, pick from §12 stretch goals.

---

## 1. What we're building (in one breath)

Three AI agents orchestrated as a **LangGraph stateful agent graph**, forming a **self-improving learning loop for newsroom content traffic**:

> **SELECT** the stories worth covering (ranked via multi-dimensional scoring) → **PRODUCE** a brief, ideal headlines, and platform versions (RAG-grounded, tool-called) → **MEASURE** how it performed (via LLM-as-a-judge evals) → feed that back so the next SELECT is smarter.

A human approves between SELECT and PRODUCE. Everything runs locally with synthetic, read-only data. Built on **Gemini Enterprise**, with full **LLM tracing and observability**. The demo's job is to make the judges *see the loop close* — rankings visibly change after feedback — and to claim a concrete **>70% editorial-prep time saving**.

## 2. Scope

**In scope (build these):**
- 3 agents: Content Selection, Content Production (RAG-grounded), Audience Telemetry
- LangGraph orchestrator with cyclic graph, human-in-the-loop interrupt, and checkpointing
- RAG layer: vector store (FAISS/Chroma) + embeddings for grounding and reusable-asset surfacing
- Gemini function calling for tool-calling + structured JSON output
- LLM-as-a-judge eval gate for quality scoring before output
- LLM tracing + OpenTelemetry spans + in-app trace panel
- Mock data layer (candidate stories, synthetic GA4, feedback signal table)
- Approval gate (editor: 1 tap)
- Streamlit UI with rank-shift badges and feedback loop visualization
- 3-minute live demo script

**Out of scope (say this out loud if asked):**
- Real newsroom systems, Gemini Enterprise production setup, cloud deployment
- Full OpenTelemetry dashboards (Jaeger/Grafana) — thin in-app panel only
- Live news APIs, real GA4, real reporter material (synthetic only)
- Write-back into editorial tools, full governance guardrails
- The other 6 agents from the original deck (Folo, Re-use, Media Collection, etc.)
- Corrective-edit feedback loop (Telemetry → Production) — this is a stretch goal
- Real-time live engagement (simulated for the demo)

### 2.1 Deck ↔ code alignment (read before you present)

The pitch deck headlines **two** agents — Content Selection and Audience Telemetry — as the core PoC. This build has **three**, adding **Content Production** in the middle. Reconcile this so a judge with the deck open doesn't get confused seeing a third agent on screen.

Correct framing: **Selection and Audience Telemetry form the learning loop; the Content Production agent is the production handoff between them.** It's what turns an approved pick into real, publishable output (web / social / push), so the demo shows a *pick becoming something real*, not just a score. Do **not** call Content Production the "human-in-the-loop" step — that's the **approval gate** (the editor choosing a story). Production is the handoff, the gate is the human control point.

Two acceptable ways to present it, pick one and be consistent:
- **Deck edit:** add one line to the agent slide noting Content Production as the connecting production step; or
- **Verbal:** keep the deck at two headline agents and introduce Content Production live — *"and here's how the approved story becomes real output."*

## 3. Architecture

```
 ┌─────────────┐   ┌───────────────────────────────┐   ┌───────────────┐   ┌────────────┐
 │  DATA LAYER │──▶│          ORCHESTRATOR         │──▶│ APPROVAL GATE │──▶│ STREAMLIT  │
 │ news + GA4  │   │ Select → Produce → Telemetry  │   │ editor: 1 tap │   │    UI      │
 └─────────────┘   └───────────────────────────────┘   └───────────────┘   └────────────┘
        ▲                    ▲            │                                        │
        │                    │            │                                        │
        │   (3) follow-ups   │  (2) corrective-edit feedback                       │
        │   as new candidates│      Telemetry → Produce                          │
        │                    │                                                     │
        │            (1) FEEDBACK SIGNAL TABLE — audience telemetry re-tunes SELECT       │
        └────────────────────────────────────────────────────────────────────────┘
```

Three feedback loops now run, not one: **(1)** Telemetry writes topic|geo weights to the signal table and Select reads them (the core loop, the demo money shot); **(2)** Telemetry sends corrective-edit recommendations back to Produce; **(3)** Telemetry emits follow-up story ideas that re-enter Select as new candidates. Loop 1 is PoC-core; loops 2 and 3 are the "multi-loop, self-improving" story — build them if time allows.

Everything is a function that takes JSON and returns JSON. The LLM lives inside each agent; the orchestrator just moves JSON between them. The feedback table is a plain dict/JSON that Telemetry writes and Select reads.

## 4. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.11 | |
| LLM | **Gemini (Gemini Enterprise)** | Provided to Top 30 teams. Wrap behind a single `llm(prompt, schema) -> dict` helper so it stays swappable; confirm whether you're on the Gemini API vs Vertex/Agent Studio and keep it simple |
| Orchestration | **LangGraph** | Models the loop as a stateful agent graph — cyclic edges for the feedback loop, an `interrupt` node for the approval gate, checkpointing for state |
| Grounding | **RAG — vector store (FAISS or Chroma) + embeddings** | Index source articles + the asset archive; Production retrieves to ground briefs/stories and to surface reusable assets |
| Tool use | **Gemini function calling + structured JSON output** | Agents return strict JSON; Selection/Telemetry can call analytics "tools" |
| Evaluation | **LLM-as-a-judge** | A small eval step scores ranking/headline quality and acts as a quality gate before output |
| Observability | **LLM tracing via OpenTelemetry** | Instrument the one `llm()` wrapper; surface a trace panel in the UI (thin version for PoC — see §14) |
| UI | Streamlit | Fastest path to a demoable screen |
| Data | pandas + JSON files; SQLite optional | No cloud DB |
| News (optional live) | `feedparser` on Google News RSS, or a news API | **Have a canned JSON fallback** — never demo on a live network |

**Repo layout:**
```
newsroom-poc/
  data/
    candidate_stories.json      # or generated live
    historical_performance.csv  # synthetic GA4
    feedback_signals.json       # written at runtime, starts as {}
  agents/
    selection.py
    production.py
    Telemetry.py
  core/
    llm.py                      # single Gemini wrapper: JSON parsing + tracing
    graph.py                    # LangGraph: nodes, cyclic edges, approval interrupt
    signals.py                  # read/write feedback table
    rag.py                      # vector store: index + retrieve (grounding, reuse)
    evals.py                    # LLM-as-a-judge quality gate
    trace.py                    # OpenTelemetry setup + span helpers
  gen/
    make_synthetic_data.py      # generates the two data files
  app.py                        # Streamlit UI (incl. trace panel)
  .env                          # API keys (gitignored)
  requirements.txt
```

**First-hour setup:** create the repo, `requirements.txt`, `core/llm.py` with a working "hello world" Gemini call returning parsed JSON (with a trace span around it), and commit the empty data files. Nobody builds until `llm.py` works for everyone.

## 5. Integration contracts (agree on these FIRST)

These JSON shapes are the API between workstreams. Lock them so Data, Agents, and UI can build against mocks independently. Change them only by team agreement.

### 5.1 Candidate story (input to Select)
```json
{
  "id": "s001",
  "headline": "City council approves new transit budget",
  "topic": "local-government",
  "geo": "Baltimore",
  "source": "rss",
  "published_at": "2026-09-02T08:10:00Z"
}
```

### 5.2 Historical audience performance (synthetic GA4, one row per past story)
CSV columns: `story_id, topic, geo, demographic, page_views, avg_time_on_page_sec, shares, likes, comments, subscriptions_driven, revenue_usd`

### 5.3 Ranked story (output of Select → shown in UI)
```json
{
  "id": "s001",
  "headline": "City council approves new transit budget",
  "score": 0.87,
  "why_it_matters": "High engagement on local-government in this geo; recurring subscriber driver.",
  "suggested_angle": "Focus on rider impact and cost per household.",
  "timing": "Publish before 5pm for commute traffic."
}
```
Select returns `{"ranked": [ ...top 5... ]}`.

### 5.4 Telemetry result (output of Telemetry → written to feedback table)
```json
{
  "story_id": "s001",
  "topic": "local-government",
  "geo": "Baltimore",
  "engagement_score": 0.91,
  "insight": "Outperformed baseline by 40%; strong share rate.",
  "weight_delta": +0.15
}
```

### 5.5 Feedback signal table (the loop's memory) — `feedback_signals.json`
```json
{ "local-government|Baltimore": 0.15, "sports|Baltimore": -0.05 }
```
Key = `"{topic}|{geo}"`, value = accumulated weight. **Select adds this weight to its base score for matching stories.** This single dict is why round 2 differs from round 1.

## 6. The three agents

Each agent = a prompt + the `llm()` wrapper + strict JSON output. Keep prompts in the agent file as a constant. Tell the model: *"Return ONLY valid JSON matching this schema, no prose, no markdown fences."* Then strip fences defensively before parsing.

### Agent 1 — Content Selection (`agents/selection.py`)
- **In:** list of candidate stories (§5.1) + historical performance (§5.2) + feedback table (§5.5)
- **Job (PoC core):** score each candidate on predicted engagement/revenue/fit; add feedback weight for matching topic|geo; return top 5.
- **Out:** `{"ranked": [RankedStory, ...]}` (§5.3)
- **Prompt sketch:** "You are a newsroom analytics director. Given these candidate stories, this historical performance summary, and these learned topic weights, score each story 0–1 for likely audience engagement and revenue, factoring the learned weights. Return the top 5 as JSON with score, why_it_matters, suggested_angle, timing."
- **Tip:** pre-aggregate the CSV in Python (avg engagement per topic|geo) and pass a compact summary to the LLM, not 500 raw rows.
- **Full capability (from the deck — wire in if time allows):** the agent is meant to blend **internal data** (historical performance, audience insights, ratings & engagement, subscription data, revenue metrics) with **external signals** (social trends, news feeds, community discussions, competitor coverage, public events & civic data, search trends, plus reader comments and social-listening chatter), and to **detect emerging topics** — i.e. surface *new* candidate topics from those signals, not only rank a fixed list. For the PoC, fake the external signals as extra fields on the candidate stories; treat live signal ingestion as a stretch goal.
- **Multi-dimensional scoring (deck slide 16 — easy, high demo value):** instead of one blended score, score each story on four named dimensions and show them in the UI:
  - `human_story_value` — will this benefit from real human storytelling (vs commodity news)?
  - `cut_through` — likelihood of breaking through algorithmic discovery/recommendation feeds.
  - `demographic_monetization` — value against high-worth demographics.
  - `brand_loyalty` — potential to build audience trust and loyalty.
  The overall `score` becomes a weighted blend of these. Add them to the RankedStory output (§5.3) as a `scores` object.
- **Follow-up candidates in (closes a second loop):** Selection should also accept *follow-up suggestions* produced by the Telemetry agent (see Agent 3) and treat them as new candidate stories, so strong stories spawn their next round.

### Agent 2 — Content Production (`agents/production.py`)
- **In:** one approved RankedStory (plus, when available, the source article text / reporter material to ground it — see below)
- **Job (PoC core):** turn the approved pick into publish-ready output — reporter prep, **ideal headlines**, and three platform versions. This now absorbs the old Reporting Agent's prep function, so one agent covers *both* prep and production.
- **Out:**
```json
{
  "brief": {
    "background_research": "context and key facts on the story",
    "key_questions": ["what the piece must answer"],
    "interview_guidance": {
      "who_to_interview": ["roles/sources to contact"],
      "questions_to_ask": ["suggested interview questions"]
    },
    "content_to_collect": ["footage, docs, data, on-site assets to gather"],
    "soundbite_guidance": ["soundbite types to capture for the target platforms"],
    "shot_list": ["specific shots / visuals, optimized for target platforms"],
    "reusable_assets": ["existing/archived stories or media that can be reused here"],
    "missing_assets": ["items on the collection list not yet gathered"]
  },
  "versions": {
    "web": {"headline": "...", "dek": "..."},
    "social": [{"account": "flagship", "audience": "general", "caption": "...", "hashtags": ["..."]},
               {"account": "younger-demo", "audience": "18-34", "caption": "...", "hashtags": ["..."]}],
    "push": {"title": "...", "body": "..."},
    "broadcast": {"linear_script": "...", "on_screen_text": ["..."]},
    "cross_market": [{"market": "other-geo", "adaptation_notes": "..."}]
  }
}
```
- **Platform-targeted prep (Reporting Agent, slide 16):** the shot list, soundbite types, and questions are generated *for the specific target platforms and their KPIs*, not generically — pass the target platforms into the prompt so prep is platform-aware.
- **RAG grounding (core PoC feature):** Production retrieves similar past stories from a vector store before drafting. This grounds the `background_research`, `interview_guidance`, and any story body in *real reporting* rather than LLM invention. Add a `rag.py` helper that (1) embeds the approved story headline/topic, (2) retrieves top-2 similar stories from the index, and (3) passes that context into the agent prompt with "Base all facts and angles on the provided retrieved stories — do not invent." This also surfaces reusable assets automatically.
- **Reusable-asset surfacing (Reporting + Re-use Agents):** the retrieved stories *are* your reusable assets — use them directly in `reusable_assets`. The RAG step does the work.
- **Missing-asset gap check (Media Collection Agent, slide 16):** given a "collected so far" list, compare against `content_to_collect` and return what's still missing → `missing_assets`. (Skips the heavy transcription/scene-analysis parts, which are roadmap.)
- **Richer versions (Versioning Agent, slide 17):** produce per-account/per-audience social variants (not one caption), a broadcast/linear script with on-screen text, and cross-market adaptation notes — all text, so cheap to add.
- **Gemini function calling (structured tool-calling, core PoC):** the agent calls a `retrieve_assets(topic, geo)` tool (which fetches from the vector store) and a `validate_json(schema)` tool, returning strict structured JSON. This demonstrates proper agentic tool use.
- **Prompt sketch:** "You are an executive producer and assignment editor. For this story, angle, and target platforms, (1) call retrieve_assets(topic, geo) to ground yourself in past reporting, (2) produce a platform-aware prep brief — background research (grounded in the retrieval), key questions, interview guidance, content + soundbites + shots to collect, reusable assets (from the retrieval), and a gap check — and (3) produce publish-ready output: ideal headlines and versions for web, per-audience social accounts, push, broadcast script, and cross-market adaptations. Return JSON matching [schema]. Validate with validate_json."
- **Full-story option (team to decide — fabricated vs. real source material):** add a `"story"` block (`headline`, `subhead`, `body`, `seo_slug`) when you want the whole article drafted. RAG grounding makes this defensible; without it, label it "AI draft — pending editorial review."

### Agent 3 — Audience Telemetry (`agents/telemetry.py`)
- **In:** the published story + its engagement metrics (page views, unique users, time on page, shares/likes/comments, SEO metrics, conversions & revenue)
- **Job (PoC core):** analyze audience performance telemetry via LLM-as-a-judge, write an insight, output a `weight_delta` for the feedback table.
- **LLM-as-a-judge eval (core PoC feature):** instead of just comparing metrics to a threshold, send the story + metrics to an LLM with a grading rubric: "Grade this story's audience performance (0–1) on: engagement, monetization, brand fit, and repeat-audience rate. Return JSON with score, reasoning, and a recommended weight_delta for next round." This quality gate proves the system isn't just averaging; it's *reasoning* about audience response. Use the same Gemini wrapper so it shows up in traces.
- **Out:** TelemetryResult (§5.4) + structured `eval_reasoning`
- **The simulation:** we can't get real engagement in a demo. `gen/` produces plausible metrics biased by the story's Select score (good picks tend to do well, with noise) OR the UI lets the presenter type "it did great / poorly". The LLM-as-a-judge step adds credibility by reasoning about the result, not just scoring it mechanically.
- **Full capability (from the deck — stretch/roadmap):** beyond scoring one story, the agent is meant to do **audience segmentation** (demographics, interests, segments & cohorts, personas), **trend & opportunity identification**, **predictive performance modeling** (engagement/traffic/revenue forecasts, not just past scoring), and produce **recommendations** (content ideas & growth opportunities) plus **impact reports**. For the PoC, the one output that must exist is the `weight_delta` that closes the loop; the richer segmentation/forecasts/recommendations are stretch outputs you can add to the insight text or extra JSON fields if time allows.
- **Second feedback loop — Telemetry → Production (deck slide 17, biggest add):** feed performance insights back into the Production agent as **corrective-edit recommendations** — lean into moments that performed, cut/replace segments with high abandonment, re-tag or re-post for accounts that drove reach. This gives the demo a *second* visible loop on top of Telemetry → Selection. Add a `production_feedback` block to the output. Moderate effort.
- **Segment / moment-level + abandonment analysis (slide 17):** analyze *which parts* of a story worked vs where audiences dropped off, not just a story-level number. Needs segment-level mock data; add `segment_analysis` and `abandonment_points`. Moderate.
- **Follow-up suggestions (Folo Agent, slide 17):** after a story performs, output follow-up/adjacent story ideas, angles, and expert sources → `follow_ups`, and hand these to Selection as new candidate stories. This folds the Folo Agent in and enriches the Selection loop. Easy, text-only.
- **Extended output (add to §5.4 when you build these):**
```json
{
  "story_id": "s001", "topic": "...", "geo": "...",
  "engagement_score": 0.91, "insight": "...", "weight_delta": +0.15,
  "segment_analysis": [{"segment": "18-34", "engagement": 0.8}],
  "abandonment_points": ["drop-off after intro"],
  "production_feedback": ["lengthen the performant opening", "cut the slow middle segment"],
  "follow_ups": [{"idea": "...", "angle": "...", "expert": "..."}]
}
```
- **Be honest in the pitch:** "in production this reads real GA4; for the demo we model it."

## 7. Work breakdown & ownership

Five workstreams. With 3 people, merge C into B and E into whoever owns the deck.

| # | Workstream | Owner | Key deliverables | Depends on |
|---|---|---|---|---|
| A | **Data & Signals** | | `make_synthetic_data.py`, the two data files, canned news JSON, `signals.py` read/write | Contracts (§5) |
| B | **Agents** | | `selection.py`, `production.py`, `telemetry.py` with locked prompts + JSON out | §5, `llm.py` |
| C | **Orchestration & Loop** | | `orchestrator.py`: run Select → gate → Produce → Telemetry → update table → re-run | A, B |
| D | **UI** | | `app.py`: 3 screens + "Run again" button | §5 (can mock B) |
| E | **Demo & Deck** | | 3-min script, run-through, talking points, deck edits | everything by Phase 4 |

**Parallelism trick:** because everyone builds against the §5 JSON contracts, D can build the UI with hard-coded sample JSON before B's agents are ready, and B can test agents with A's static files before C's orchestrator exists. Wire together in Phase 2.

## 8. Timeline

| Phase | Window | Goal | Exit criteria |
|---|---|---|---|
| **0 — Setup** | first 2 hrs | Repo, Gemini API key, LangGraph spike, `core/llm.py` + tracing, RAG setup (FAISS + sample data), contracts locked | Everyone can: make one Gemini call returning JSON w/ trace, query the vector store, run LangGraph locally |
| **1 — Vertical slice** | to ~hr 10 | Selection works on real data, RAG index built, tool-calling wired | `python -m core.orchestrator` prints a ranked list; retrieve_assets(topic) works |
| **2 — Close the loop** | to ~hr 18 | Production (RAG-grounded) + Telemetry (LLM-as-a-judge evals) + feedback table wired; round 2 differs from round 1 | Running twice: rankings visibly change; eval_reasoning is written; traces appear in logs |
| **3 — UI** | to ~hr 28 | Streamlit shows: rankings (w/ badges) → approve → produce (show RAG-retrieved context) → audience telemetry (show eval reasoning) → re-run; trace panel visible | Full flow clickable; rank-shift badges working; trace panel shows agent calls |
| **4 — Demo polish** | last 6 hrs | Rehearse, canned-data fallback, error handling, timing, deck refresh | Two clean run-throughs under 3 min; observability/tracing story is clear |

**Rule:** hit "loop closes" (end of Phase 2) with RAG grounding and LLM-as-a-judge working before touching UI. A working loop with evals and tracing in a terminal beats a beautiful UI without the AI depth.

## 9. Streamlit UI — three screens

1. **Rankings** — table of top 5 with score + why_it_matters; a "Select this story" button per row (the approval gate).
2. **Brief & Versions** — the reporter brief, headlines, plus three cards (web / social / push) rendered side by side.
3. **Audience Telemetry & Loop** — show the (simulated) metrics + insight, a "Publish feedback" button, then a **"Re-run Selection"** button. When clicked, screen 1 reloads with visibly reordered rankings.

**Make the rank shift unmistakable (do not skip — this is the demo's money shot).** Before re-running, save each story's round-1 position into `st.session_state["prev_ranks"]` (a `{story_id: rank}` dict). When round 2 renders, per row show:
- a **position badge**: `▲2` (moved up 2), `▼1` (moved down 1), `—` (unchanged), or `NEW` if it wasn't in round 1;
- the **weight that caused it**: `+0.15` pulled from the feedback table for that story's `topic|geo`;
- **row color**: green tint for rows that moved up, red tint for down, so a judge sees the change at a glance without reading text.

The goal: a judge glances at the screen and *instantly* sees feedback reshaped the rankings. If they have to diff two tables in their head, the moment is lost.

Keep it single-page with `st.session_state` holding the current story, versions, the feedback table, and `prev_ranks`.

## 10. Demo script (~3 min)

1. *"An editor faces 100 story options every morning and picks by gut."* → click Run, top 5 appear in seconds with reasoning. **(SELECT)**
2. *"They approve one."* → one click. **(GATE)**
3. *"The AI drafts the brief and every platform version — the approved pick becomes real output."* → show the three cards. **(PRODUCE / handoff)**
4. *"It publishes, the audience reacts — and here's the part that matters."* → show audience telemetry, hit Publish feedback. **(TELEMETRY)**
5. *"Re-run tomorrow's picks."* → rankings visibly change. *"The system just learned."* **(LOOP CLOSES — the money shot.)**
6. Land the number: *"~30 minutes of manual triage → ~10 seconds. Over 70% of prep time back."*

Assign one driver (clicks) and one narrator. Rehearse twice.

## 11. Risks & mitigations

- **LLM returns bad JSON** → wrap every call in try/parse, strip ```` ```json ```` fences, retry once with "return valid JSON only". Build this into `llm.py` so all agents inherit it.
- **Live news API flakes on stage** → default to canned `candidate_stories.json`; make live news a toggle, not the demo path.
- **Simulated performance looks fake** → bias metrics by Select score + small random noise so good picks trend well; keep the insight text LLM-generated so it reads real.
- **LLM latency kills the demo** → cap the on-stage candidate pool at **~15 stories** (keep a larger pool only if you pre-compute its result). Pre-run round 1 before presenting and cache it in `st.session_state` so the first click is instant. Realistic target is **under ~3s per call, and instant for anything pre-cached** — a single cold Select call over 15 stories is often 3–6s, so don't promise sub-2s on a live path. If you need sub-2s determinism on stage, pre-compute *both* rounds and let the buttons reveal cached results. Note: "pre-warming model caches" isn't a real lever — you don't control the provider's cache; what you control is pool size, prompt length, and your own caching.
- **Scope creep** → the other 6 agents and any cloud/deployment work are explicitly banned until §12.
- **Merge chaos** → the §5 contracts are frozen; changing one requires a 30-second team huddle.

## 12. Definition of done & stretch goals

**Done =** full flow runs in Streamlit, the loop demonstrably changes rankings after feedback, canned-data fallback works, and two people can narrate it in under 3 minutes.

**Stretch (only after Done):**
- Live Google News RSS as the real candidate source
- A tiny before/after "time saved" counter on screen
- A second geo to show the feedback table specializing by location
- Search-grounded trending topics via the LLM's web/grounding tool
- Persist the feedback table to SQLite so "learning" survives restarts

## 14. Observability & Governance

Treat these as two tiers: a **thin version you actually build** (for credibility in the demo) and a **full version you present as the production roadmap**. Don't build the heavy version in 24 hours.

**Build for the demo (a few hours, high judge value):**
- **LLM tracing in one place.** Instrument the single `core/llm.py` wrapper so every agent call records: agent name, loop round, prompt, response, token counts, latency, and pass/fail of the eval gate. Because all three agents call this wrapper, you get full tracing for free.
- **OpenTelemetry spans.** Emit each call as an OTel span from `core/trace.py`. Even logging spans to console/in-memory is enough to say "traced via OpenTelemetry" honestly.
- **Trace panel in the UI.** A collapsible panel in Streamlit that lists the spans for the last run (who called Gemini, with what, how long). This visibly proves the system isn't a black box.
- **Audit trail = governance you already have.** Log every editor approval and every `weight_delta` with a timestamp. That log *is* your audit trail — no extra framework needed.
- **Output guardrails (light).** Validate every agent's JSON against its schema and reject/retry on failure; add a simple check that flags AI-drafted content as "pending editorial review."

**Present as roadmap (name, don't build):**
- Full OpenTelemetry export to a backend (Jaeger / Grafana / Cloud Trace) with latency/error/throughput dashboards.
- AI-governance layer: policy controls, bias/accuracy monitoring, and Gemini/Vertex safety tooling (e.g. Model Armor, safety filters) for output guardrails.
- Per-agent cost/token budgeting and alerting.

**Framing discipline (so it stays defensible):** the feedback mechanism is **reward-driven re-ranking / weighted feedback**, not reinforcement learning; say "RAG-grounded," "structured tool-calling," and "LLM-as-a-judge" only for the parts you actually build. Accurate depth beats inflated claims with technical judges.

## 15. First-hour checklist

- [ ] Repo created, pushed, everyone cloned
- [ ] `requirements.txt` + virtualenv working for all; key packages: `langraph`, `langgraph-cli`, `faiss-cpu` (or `chroma`), `opentelemetry-api`, `opentelemetry-sdk`
- [ ] Gemini API key(s) in `.env`; confirm whether using plain Gemini API or Vertex/Agent Studio
- [ ] `core/llm.py` makes one Gemini call returning parsed JSON (with a try/trace span around it)
- [ ] `core/rag.py` can embed a test story and query the FAISS index; sample embedded stories committed
- [ ] `core/graph.py` imports LangGraph and defines a toy 2-node graph that runs without error
- [ ] `core/trace.py` can emit OTel spans to console (no backend needed yet)
- [ ] §5 contracts pasted into the repo README and agreed
- [ ] Owners assigned to workstreams (Data, Selection, Production, Audience Telemetry, Orchestration, UI)
- [ ] Stub data files + mock vector store committed so all workstreams can start against mocks in parallel
