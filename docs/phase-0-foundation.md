# NewsForge — Phase 0 Foundation

## Purpose

Phase 0 locks the implementation contracts for NewsForge before backend and AI work starts. The existing Vite frontend remains a public-reader prototype until Phase 1 moves it to the final application structure.

## Product boundaries

| Area | Phase 0 decision |
| --- | --- |
| Public brand | **NewsForge** |
| Editorial workspace | **NewsForge Studio** |
| AI workflow | **NewsForge AI Engine** |
| Public reader | React/Vite, later migrated to Tailwind CSS + shadcn/ui |
| API | Python 3.11+, FastAPI, `/api/v1` |
| Database | MongoDB, accessed asynchronously with Motor |
| Object storage | S3-compatible API; MinIO locally |
| AI execution | Gemini Enterprise through approved Google Cloud credentials; FastAPI backend only |
| Local deployment | Native frontend/backend development or Docker Compose |

## Roles and authorization

| Role | Permissions |
| --- | --- |
| `admin` | Manage users, roles, all content, agent settings, and platform configuration. |
| `editor` | All editorial, AI, taxonomy, and platform capabilities except user management. |

All protected APIs require a verified JWT. User management is enforced as admin-only by the backend; hiding the Studio section is not the authorization mechanism.

## Article lifecycle

```text
lead → ranked → approved → draft → in_review → scheduled → published → archived
                         └────────────→ rejected
draft / in_review / scheduled / published → archived
```

- An AI Selection result creates or updates a `lead`.
- Only an `editor` or `admin` can approve a lead, publish, unpublish, or schedule.
- AI Production output always enters as a `draft`; it is never auto-published.
- Every state transition creates an immutable workflow event.

## Core MongoDB collections

### `users`

```json
{
  "_id": "ObjectId",
  "email": "editor@newsforge.example",
  "password_hash": "bcrypt hash",
  "display_name": "Maya Chen",
  "role": "editor",
  "avatar_media_id": "ObjectId | null",
  "is_active": true,
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601"
}
```

### `articles`

```json
{
  "_id": "ObjectId",
  "slug": "a-city-designed-for-the-heat-to-come",
  "status": "draft | in_review | scheduled | published | archived",
  "title": "A city designed for the heat to come",
  "dek": "Short article introduction",
  "content_json": {},
  "content_html": "<p>Rendered editor content</p>",
  "hero_media_id": "ObjectId | null",
  "topic": "climate",
  "tags": ["cities", "design"],
  "creator_id": "ObjectId",
  "editor_id": "ObjectId | null",
  "published_at": "ISO-8601 | null",
  "scheduled_for": "ISO-8601 | null",
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601",
  "metrics": {
    "views": 0,
    "likes": 0,
    "dislikes": 0,
    "engagement_ratio": 0,
    "popularity_score": 0,
    "seo_score": null
  }
}
```

### Supporting collections

- `media`: file metadata, object key, MIME type, size, uploader, public URL, timestamps.
- `feedback_events`: one raw like/dislike/view event per anonymous visitor or authenticated account.
- `telemetry_rollups`: daily and article-level aggregated metrics.
- `leads`: RSS/wire input, source metadata, ranking scores, and editorial decision.
- `ranking_signals`: learned topic/geo weights used by Selection.
- `agent_runs`: input snapshot, output, model/provider, prompt version, status, timings, and errors.
- `workflow_events`: immutable editorial state transition history.

## Required indexes

```text
users.email                         unique
articles.slug                       unique
articles.status + scheduled_for
articles.status + published_at
articles.topic + metrics.popularity_score
feedback_events.article_id + actor_key + day  unique
leads.source_url                    unique when available
agent_runs.created_at
```

`actor_key` is an authenticated user ID when available, otherwise a privacy-preserving browser identifier. The unique feedback index prevents repeated likes/dislikes from inflating a story's score.

## API contract conventions

- Prefix every route with `/api/v1`.
- JSON uses `snake_case`; frontend adapters may map to camelCase if desired.
- Dates are UTC ISO-8601 strings.
- Lists return `{ "items": [], "page": 1, "page_size": 20, "total": 0 }`.
- Errors return `{ "detail": "human-readable message", "code": "STABLE_ERROR_CODE" }`.
- Write APIs return the latest canonical server document.
- IDs are strings at the API boundary, never MongoDB ObjectIds.

## Initial endpoints

| Area | Endpoint | Purpose |
| --- | --- | --- |
| Health | `GET /api/v1/health` | Service/readiness check. |
| Auth | `POST /api/v1/auth/login`, `GET /api/v1/auth/me` | Identity lifecycle; administrators create accounts. |
| Articles | `GET /api/v1/articles`, `GET /api/v1/articles/{slug}` | Public feed and reader. |
| Feedback | `POST /api/v1/articles/{id}/feedback` | Accept `like` or `dislike`; return fresh metrics. |
| CMS | `POST /api/v1/cms/articles`, `PATCH /api/v1/cms/articles/{id}`, `POST /api/v1/cms/articles/{id}/publish` | Editorial workflow. |
| Media | `POST /api/v1/media/upload` | Upload to MinIO/S3 and return media metadata. |
| Agents | `POST /api/v1/agents/selection/run`, `POST /api/v1/agents/produce`, `POST /api/v1/agents/telemetry/recalculate` | Explicit human-triggered agent runs. |

### Feedback request and response

```json
POST /api/v1/articles/ARTICLE_ID/feedback
{ "action": "like" }
```

```json
{
  "article_id": "ARTICLE_ID",
  "viewer_action": "like",
  "metrics": {
    "views": 125,
    "likes": 32,
    "dislikes": 3,
    "engagement_ratio": 0.914
  }
}
```

## AI-engine rules

1. Every agent accepts and returns validated Pydantic models.
2. Agent inputs, outputs, model/provider, prompt version, and errors are recorded in `agent_runs`.
3. An agent cannot publish or modify a public article directly.
4. Production content is marked AI-assisted and enters the draft/review workflow.
5. Telemetry updates `ranking_signals`; Selection consumes those signals on its next run.
6. Live feeds and LLMs must have deterministic fixture fallbacks for local development and demos.

## Gemini Enterprise implementation plan

NewsForge uses Gemini Enterprise as its primary AI platform. The FastAPI service owns all Gemini calls; browsers receive only validated agent results and never Google credentials or provider tokens.

### Provider boundary

```text
Selection / Production / Telemetry agent
              ↓
       GeminiProvider interface
              ↓
 Gemini Enterprise / Vertex AI client
              ↓
 structured Pydantic result + agent_run audit record
```

The application exposes a small internal interface:

```python
generate_json(task, prompt, response_schema, tools=None) -> dict
generate_text(task, prompt, tools=None) -> str
embed(texts) -> list[list[float]]
```

This prevents provider-specific code from spreading into agents, routes, or the CMS. A deterministic `MockGeminiProvider` is mandatory for tests, local work without enterprise credentials, and demo fallback.

### Model routing

| Workload | Default model class | Guardrails |
| --- | --- | --- |
| Content Selection | Gemini Flash-class model | Low temperature; JSON schema only; rank at most configured number of leads. |
| Content Production | Gemini Pro-class model for article draft; Flash-class model for short social/push variants | Human approval required before publication; retrieved evidence is included in prompt. |
| Audience Telemetry | Gemini Flash-class model | JSON schema only; agent can propose, never directly apply, a weighting change above configured bounds. |
| Embeddings/RAG | Google embedding model approved in the enterprise project | Source chunks include article/media provenance and access scope. |

Actual model IDs are configuration values, not hard-coded. This accommodates the models enabled for the NewsForge Google Cloud project.

### Authentication and deployment

- **Local development:** Application Default Credentials (ADC) via approved user credentials or service-account impersonation. Do not store service-account JSON keys in the repository.
- **Google Cloud deployment:** attach a least-privilege service account to the workload; use its ADC automatically.
- **Non-Google deployment:** use workload identity federation, not downloaded long-lived credential files.
- Access requires the Google Cloud project, region, Gemini Enterprise/Vertex AI enablement, and IAM permissions to be confirmed by the cloud administrator before Phase 6 begins.

### Safety, governance, and observability

- Persist prompt template version, model ID, token/usage metadata when available, latency, tool calls, input references, output, and failure reason in `agent_runs`.
- Redact passwords, JWTs, API keys, and personal data not required for the editorial task before sending prompts.
- Apply explicit tool allowlists. Gemini function calls may read RSS, approved article context, and telemetry summaries; they cannot publish, delete media, or alter users.
- Validate every structured model response with Pydantic before it is persisted or rendered.
- Store citation/provenance references with AI drafts so editors can review their grounding material.
- Set per-agent timeout, retry, token, and daily-budget limits. Failure falls back to a reviewable mock/error state rather than blocking the CMS.

### Phase changes caused by Gemini Enterprise

| Phase | Gemini-specific work |
| --- | --- |
| Phase 0 | Confirm Google Cloud project, supported Gemini interface, region, IAM owner, and approved models. |
| Phase 2 | Add backend configuration validation and Docker-friendly mock mode; production uses ADC rather than an API key. |
| Phase 6 | Implement `GeminiProvider`, structured JSON schemas, tool declarations, RAG/embeddings, tracing, and agent-run audit history. |
| Phase 7 | Display model provenance, agent status, source context, and human-approval state in NewsForge Studio. |
| Phase 8 | Add spend/usage alerts, IAM review, data-retention review, red-team tests, and production monitoring. |

## Environment contract

```dotenv
# App
APP_ENV=development
API_V1_PREFIX=/api/v1
JWT_SECRET=replace-with-a-long-random-secret
JWT_ACCESS_TOKEN_MINUTES=30

# MongoDB
MONGODB_URI=mongodb://mongo:27017
MONGODB_DATABASE=newsforge

# S3 / MinIO
S3_ENDPOINT_URL=http://minio:9000
S3_REGION=us-east-1
S3_BUCKET=newsforge-media
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin

# Gemini Enterprise / Vertex AI (production uses ADC, not a browser key)
LLM_PROVIDER=mock
GOOGLE_CLOUD_PROJECT=
GOOGLE_CLOUD_LOCATION=us-central1
GEMINI_SELECTION_MODEL=
GEMINI_PRODUCTION_MODEL=
GEMINI_TELEMETRY_MODEL=
GEMINI_EMBEDDING_MODEL=

# Existing browser-only integrations
VITE_OPENWEATHER_API_KEY=
VITE_GEOAPIFY_API_KEY=
```

Secrets belong only in ignored `.env` files or deployment secret stores. `.env.example` holds placeholders only.

## Definition of done for Phase 0

- [x] NewsForge brand and product boundaries fixed.
- [x] Roles, lifecycle, collection design, indexes, and endpoint conventions recorded.
- [x] Feedback and agent-control contracts defined.
- [x] Security boundaries and environment contract recorded.
- [ ] Google Cloud project, region, approved Gemini models, and IAM owner confirmed.
- [ ] Team approves this document before Phase 1 implementation begins.
