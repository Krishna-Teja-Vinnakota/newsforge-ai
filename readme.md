# NewsForge AI

NewsForge AI is an editorial platform with a public news experience, a role-aware newsroom workspace, and a human-controlled AI desk. It helps editorial teams move a story from lead intake and AI ranking through approval, drafting, review, publishing, and audience-feedback-informed reranking.

## What is in this repository

- **Public reader (`frontend/`)** — React/Vite news site with article feeds, article reading, trending stories, weather/location utilities, and reader feedback controls.
- **NewsForge Studio (`studio/`)** — React/Vite editorial application for story management, rich-text editing, media upload, taxonomy, users, profiles, and the AI desk.
- **Backend (`backend/`)** — FastAPI API with JWT authentication, role and ownership checks, article lifecycle management, telemetry, media storage, AI-agent services, and LangGraph workflow orchestration.
- **MongoDB** — primary datastore for users, articles, leads, workflow history, telemetry, and agent-run records.
- **MinIO** — S3-compatible local object storage for uploaded media.

## Editorial workflow

```text
lead → ranked → approved → draft → in_review → scheduled → published → archived
                         └──────────────────────────────→ rejected
```

The AI workflow follows `intake → selection → human approval → retrieve/draft → editorial review → publish → telemetry → rerank`. AI output is always reviewable: the production agent creates a draft and cannot publish an article on its own.

## Tech stack

| Area | Technology |
| --- | --- |
| Public site and Studio | React, TypeScript, Vite, Tiptap |
| API | Python 3.11, FastAPI, Pydantic |
| Workflow | LangGraph |
| Data | MongoDB via Motor |
| Media | S3-compatible storage; MinIO locally |
| AI | Gemini Enterprise-compatible provider with deterministic mock mode |
| Local environment | Docker Compose |

## Quick start with Docker

### Prerequisites

- Docker Desktop (or Docker Engine with Compose)

### Start the platform

```bash
git clone <repository-url>
cd newsforge-ai
docker compose up --build
```

This starts the full local stack:

| Service | URL |
| --- | --- |
| Public reader | http://localhost:5173 |
| NewsForge Studio | http://localhost:5174 |
| API and OpenAPI docs | http://localhost:8000/api/v1/health · http://localhost:8000/docs |
| MinIO console | http://localhost:9001 |
| MinIO S3 API | http://localhost:9000 |
| MongoDB | `mongodb://localhost:27017` |

The default configuration uses mock AI, so a Gemini credential is not required for local development. The backend bootstraps an administrator using the Docker Compose defaults:

```text
Email:    admin@newsforge.dev
Password: NewsForgeAdmin#2026
```

Change these values before exposing any environment beyond local development.

Stop the stack with `docker compose down`. Use `docker compose down -v` only when you intentionally want to remove local MongoDB and MinIO data.

## Configuration

NewsForge uses one root `.env` file for Compose. Create it once with
`cp .env.example .env`; `.env.example` is safe to commit, while `.env` is
ignored and is where credentials belong.

Important backend settings:

| Variable | Purpose |
| --- | --- |
| `MONGODB_URI`, `MONGODB_DATABASE` | MongoDB connection and database |
| `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_*` | MinIO/S3 media storage |
| `JWT_SECRET` | JWT signing key; use a non-default secret in production |
| `BOOTSTRAP_ADMIN_*` | Local/bootstrap administrator details |
| `LLM_PROVIDER` | `gemini_enterprise` for Gemini, or `mock` for deterministic local fixtures |
| `ENABLE_MOCK_AI` | Enables deterministic local AI responses when the provider is `mock` |
| `GEMINI_API_KEY`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` | Gemini provider configuration |
| `GEMINI_SELECTION_MODEL`, `GEMINI_PRODUCTION_MODEL`, `GEMINI_TELEMETRY_MODEL` | Per-agent model selection |
| `AGENT_TIMEOUT_SECONDS`, `AGENT_MAX_WEIGHT_DELTA` | Agent execution and bounded learning-loop controls |

For Gemini, set `LLM_PROVIDER=gemini_enterprise` and provide the Google Cloud/Gemini values through your environment or secret manager. Browser applications never receive Gemini credentials.

## Repository structure

```text
newsforge-ai/
├── backend/
│   ├── app/
│   │   ├── agents/          # selection, production, telemetry, provider, graph
│   │   ├── api/routes/      # FastAPI route handlers
│   │   ├── core/            # settings, security, database, storage, feature flags
│   │   ├── middleware/      # audit logging and rate limiting
│   │   ├── models/          # Pydantic request/response models
│   │   └── services/        # articles, users, content, telemetry, agent runs
│   ├── scripts/             # demo and bulk-data seed scripts
│   ├── tests/               # unit and integration tests
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   └── src/                 # public reader UI, services, repositories, types
├── studio/
│   └── src/
│       ├── app/             # Studio application shell
│       ├── features/        # stories, AI desk, users, taxonomy, profile, auth
│       └── shared/          # Studio API client
├── docs/                    # architecture and phased implementation docs
├── docker-compose.yml       # MongoDB, MinIO, API, public reader, Studio
├── OPERATIONS.md            # production controls, backup, recovery guidance
├── ARCHITECTURE_DECISION.md # LangGraph orchestration decision
└── DEMO_SCRIPT.md           # demo flow
```

## Key capabilities

### Public reader

- Browse public articles and trending content.
- Open full article pages and view adjacent stories.
- Capture views and like/dislike feedback for telemetry and ranking.
- Use weather and location helpers configured with browser-side API keys.

### NewsForge Studio

- Authenticate as `admin`, `editor`, `reporter`, or `audience`.
- Create and edit stories with a Tiptap rich-text editor.
- Upload hero and inline media to MinIO/S3.
- Submit drafts for review; editors and admins can approve, publish, unpublish, schedule, or archive according to role.
- Manage topics, tags, profiles, and—administrators only—users.
- Run and inspect the AI desk: lead inbox, scoring, production output, telemetry, and agent traces.

### AI engine

- **Selection agent:** ranks editorial leads using signals and produces score explanations and angles.
- **Production agent:** turns an approved lead into a grounded draft and editorial output.
- **Telemetry agent:** analyzes engagement, recommends bounded ranking-signal adjustments, and feeds the next selection cycle.
- **Workflow graph:** persists workflow state and exposes traceable human approval pauses.
- **Mock provider:** supports deterministic tests, offline local development, and demos.

## API overview

All API routes are prefixed with `/api/v1`. Interactive endpoint documentation is available at `/docs` while the API is running.

| Area | Example endpoints |
| --- | --- |
| Health | `GET /health` |
| Authentication | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` |
| Public articles | `GET /articles`, `GET /articles/trending`, `GET /articles/{slug}` |
| Feedback and telemetry | `POST /articles/{id}/view`, `POST /articles/{id}/feedback`, `GET /telemetry/signals` |
| CMS | `POST /cms/articles`, `PATCH /cms/articles/{id}`, `POST /cms/articles/{id}/submit-review`, `POST /cms/articles/{id}/publish` |
| Media | `POST /media/upload` |
| AI agents | `POST /agents/selection/run`, `POST /agents/produce`, `POST /agents/telemetry/recalculate`, `GET /agents/runs` |
| Workflow | `POST /workflow/start`, `POST /workflow/{thread_id}/resume`, `GET /workflow/{thread_id}/state` |
| Administration | `POST /admin/reset-demo`, retention-maintenance endpoints |

Protected endpoints require a verified JWT and enforce role/ownership checks in the backend.

## Quality checks

```bash
# Backend tests
cd backend
pytest

# Public reader build and typecheck
cd frontend
npm run build

# Studio build and typecheck
cd studio
npm run build
```

Optional formatting checks:

```bash
cd frontend && npm run format:check
cd studio && npm run format:check
```

## Operations and production notes

- Set `ENVIRONMENT=production`, a strong unique `JWT_SECRET`, and production MongoDB/S3 credentials before deployment. Startup rejects unsafe default development credentials in production mode.
- Use a shared persistent LangGraph checkpointer before horizontally scaling; local development uses an in-memory checkpointer.
- Back up MongoDB and the `newsforge-media` bucket, test restoration, and monitor API/MongoDB/MinIO health, agent failures, costs, and rate-limit rejections.
- Retention maintenance endpoints are admin-only. Configure `TELEMETRY_RETENTION_DAYS`, `AGENT_RUN_RETENTION_DAYS`, and `AUDIT_RETENTION_DAYS` to match policy.

See [OPERATIONS.md](./OPERATIONS.md), [ARCHITECTURE_DECISION.md](./ARCHITECTURE_DECISION.md), and [docs/phase-0-foundation.md](./docs/phase-0-foundation.md) for implementation and operational detail.
