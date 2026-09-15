# NewsForge — Complete Implementation Roadmap

This is the execution order for the complete NewsForge platform. Detailed shared contracts are maintained in [Phase 0 Foundation](./phase-0-foundation.md).

## Delivery principles

- Ship vertical slices: every phase leaves the product runnable.
- Keep public reader, Studio CMS, API, and agents independently testable.
- Use fixtures locally when external services are unavailable.
- Gemini Enterprise runs only in backend services and every output is schema-validated.
- Never block a human editorial workflow on a non-critical AI call.

## Phase 0 — Architecture and contracts

**Status:** Complete, pending infrastructure approval.

**Outputs**

- Role model, article lifecycle, MongoDB collection design, indexes, API conventions.
- Agent safety policy and Gemini Enterprise provider plan.
- Environment-variable and secrets policy.

**Decision gate**

- Confirm Google Cloud project, region, enabled Gemini models, and IAM owner.

---

## Phase 1 — Frontend application foundation

**Goal:** Turn the current NewsForge prototype into a production-shaped React application without losing the finished reader UI.

**Build**

- Add React Router routes: `/`, `/article/:slug`, `/category/:slug`, `/weather`, `/login`, `/studio`.
- Replace direct `window.location` routing and JSON imports with route-aware repository functions.
- Add Tailwind CSS, shadcn/ui, and a reusable theme provider; migrate existing CSS incrementally, page by page.
- Establish layouts: `PublicLayout`, `StudioLayout`, `AuthLayout`.
- Create reusable UI primitives: article card, author identity, metadata, empty/error/skeleton state, media image, feedback control.
- Create a typed frontend API client with mock and HTTP implementations.
- Preserve current dark mode, weather caching/location feature, trend cards, motion, and responsive layouts.

**Acceptance checks**

- Every public route works after browser refresh.
- All existing reader and weather behavior works against fixtures.
- Pages have loading, empty, and error states.
- `npm run build` and frontend typecheck pass.

**Dependency:** Phase 0 approved.

---

## Phase 2 — Backend and local platform infrastructure

**Goal:** Create the runnable FastAPI/MongoDB/MinIO foundation and containerized developer environment.

**Build**

- Add `backend/` clean-architecture directories: `core`, `models`, `api`, `services`, `repositories`, `agents`.
- Configure FastAPI, Pydantic settings, CORS, request IDs, structured logs, `/api/v1/health`, and OpenAPI tags.
- Configure Motor with MongoDB health checks and index initialization.
- Configure a MinIO/S3 client and bucket bootstrap service.
- Add Dockerfiles and `docker-compose.yml` for frontend, backend, MongoDB, MinIO, and bucket initialization.
- Maintain fixture/seed commands and the single root `.env.example` Compose template.
- Add backend test framework and API test client.

**Acceptance checks**

- `docker compose up --build` starts every service.
- API health check verifies MongoDB and object storage readiness.
- MinIO bucket exists automatically.
- Seeded public article can be returned through the API.

**Dependency:** Phase 0 approved. Phase 1 can continue in parallel once route conventions are agreed.

---

## Phase 3 — Identity, authorization, and media

**Goal:** Secure NewsForge Studio and support user-managed media.

**Build**

- JWT register, login, refresh, logout, current-user endpoints.
- Password hashing, token expiry, role checks, and ownership checks.
- User profiles: display name, role, avatar, profile updates.
- S3/MinIO media upload endpoint with MIME allowlist, file-size limit, object keys, and metadata records.
- Avatar and inline-image upload flows in the frontend.
- Audit events for authentication and sensitive role/profile changes.

**Acceptance checks**

- An Admin can assign roles; an Editor cannot administer users.
- Reporter can update their own profile and upload permitted media.
- Invalid/oversized uploads are rejected before persistence.
- Media URL behavior works both under MinIO locally and S3-compatible production configuration.

**Dependency:** Phase 2.

---

## Phase 4 — NewsForge Studio CMS and publishing

**Goal:** Deliver a complete human editorial workflow before AI automation.

**Build**

- Studio dashboard with draft, review, scheduled, and published views.
- Article create/read/update APIs with lifecycle transition rules.
- Tiptap editor: formatting toolbar, headings, lists, links, blockquotes, inline images, drag/drop upload, and autosave.
- Store canonical Tiptap JSON and sanitized rendered HTML.
- Preview modal using shared public reader components.
- Author/editor identity plus created/modified dates rendered publicly.
- Review, schedule, publish, unpublish, archive, and workflow history.

**Acceptance checks**

- Reporter creates a draft and submits it for review.
- Editor previews it accurately, schedules or publishes it, and sees it appear publicly.
- Update and publication timestamps are correct.
- Published markup is sanitized and image embeds resolve from MinIO.

**Dependency:** Phases 1–3.

---

## Phase 5 — Public telemetry and feed ranking

**Goal:** Replace mock engagement with durable first-party audience signals.

**Build**

- Public article and category feeds served by FastAPI.
- View capture, like/dislike controls, optimistic UI, and server reconciliation.
- Privacy-preserving anonymous actor identifier; authenticated actor identity where available.
- Feedback-event uniqueness and reversible like/dislike state transitions.
- Telemetry rollup service for article metrics and engagement ratio.
- Trending/popular feed query ordered by deterministic popularity score.
- Public UI migration from JSON repository to HTTP repository behind the same interface.

**Acceptance checks**

- One visitor cannot repeatedly increase a story's likes.
- Like-to-dislike changes metrics correctly.
- A newly published story appears in feeds and the ranking updates from feedback.
- The current five-item trending rail is API-backed.

**Dependency:** Phases 1–4.

---

## Phase 6 — Gemini Enterprise AI engine

**Goal:** Implement the closed-loop agent system with safe, observable, human-controlled AI output.

**Build**

- `GeminiProvider` using approved Gemini Enterprise/Vertex AI access with ADC.
- `MockGeminiProvider` for test, local, and demo fixture modes.
- Pydantic schemas and prompt templates for each agent.
- **Selection Agent:** RSS/lead input + rollups + ranking signals → ranked editorial opportunities, score breakdown, suggested angle, schedule.
- **Production Agent:** approved lead + approved context/RAG results → reporting brief, Tiptap-compatible draft JSON/HTML, social variants, push copy.
- **Telemetry Agent:** article feedback/rollups → engagement assessment, SEO/popularity prediction, bounded ranking-weight delta.
- Tool declarations for read-only trusted data retrieval only; validate all calls and results.
- `agent_runs` audit history, prompt/model provenance, latency, usage metadata, errors, retries, and limits.
- Agent trigger APIs and Studio status display.

**Acceptance checks**

- Every agent returns a validated schema or a visible failure state.
- Production output always enters as a draft, never directly published.
- Telemetry changes ranking signals within configured bounds.
- Agent results can be reproduced from captured fixture input in mock mode.
- No Gemini credentials or raw backend prompts are exposed to the browser.

**Dependency:** Phases 2, 4, and 5; Gemini project/IAM decision gate from Phase 0.

---

## Phase 7 — AI-native editorial workflow and RAG

**Goal:** Make the agent system useful inside NewsForge Studio.

**Build**

- Lead inbox with Selection Agent ranking, score explanation, and editor approval/rejection actions.
- Production workspace showing generated reporter brief, grounded source context, draft, social, and push outputs.
- Diff/review UI for accepting AI draft sections into Tiptap.
- Retrieval indexing for approved published content and media metadata; source-level provenance always shown.
- Telemetry dashboard: feedback trends, ranking shifts, SEO/popularity signals, and follow-up suggestions.
- Agent run history, failure/retry controls, and visibility into model and prompt version.

**Acceptance checks**

- Editor can approve a ranked lead, generate a draft, modify it, preview it, and publish it.
- Every visible AI claim has source context or is labelled as an editorial suggestion.
- Audience feedback produces a visible rank change in a later Selection run.

**Dependency:** Phase 6.

---

## Phase 8 — Quality, security, operations, and release

**Goal:** Make NewsForge demonstrably reliable and deployable.

**Build**

- Unit tests for domain services and agents; API integration tests; browser end-to-end workflow tests.
- Accessibility checks, responsive visual regression checks, and performance budgets.
- Rate limiting, security headers, upload scanning/validation, JWT/IAM review, and audit-log retention rules.
- Gemini Enterprise spend/usage budgets, model quotas, prompt redaction checks, and failure alerting.
- CI: format, lint, typecheck, tests, build, Docker image validation, dependency scanning.
- Production deployment documentation, database backup/restore procedure, S3 lifecycle policy, monitoring, and incident runbook.

**Acceptance checks**

- CI blocks a broken build, test, or security check.
- Full editorial path works in a staging deployment.
- Recovery procedure is tested against a MongoDB backup and media object inventory.
- Product demo can run in fixture mode if external services are unavailable.

**Dependency:** All prior phases.

## Recommended checkpoints

| Checkpoint | Result |
| --- | --- |
| After Phase 2 | Containerized platform and public API foundation. |
| After Phase 4 | Full human-run CMS with publishing. |
| After Phase 5 | Real public feedback and trending loop. |
| After Phase 6 | Safe Gemini-powered agent engine. |
| After Phase 7 | Full NewsForge AI newsroom experience. |
| After Phase 8 | Production-ready release candidate. |
