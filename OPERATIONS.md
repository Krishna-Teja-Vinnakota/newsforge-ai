# NewsForge operations guide

## Local startup

Docker: `docker compose up --build`. This starts MongoDB, MinIO, backend, public frontend, and Studio. Use mock AI by default. To use Gemini, supply `LLM_PROVIDER=gemini_enterprise`, `GEMINI_API_KEY`, `GOOGLE_CLOUD_PROJECT`, and the model variables through your environment or a secrets manager.

Native: start MongoDB (and optionally MinIO), run the backend on port 8005, Studio on 5174, and the public frontend on 5173. Set both Studio API variables to `http://localhost:8005/api/v1`. Confirm `/api/v1/health` after startup.

## Production controls

Set `ENVIRONMENT=production`, `JWT_SECRET`, and `MONGODB_URI`/`MONGO_URI` in the deployment secret store. Gemini deployments additionally require `GEMINI_API_KEY` and `GOOGLE_CLOUD_PROJECT`. Startup rejects missing/default development credentials.

Retention endpoints are admin-only: prune raw telemetry at `/api/v1/admin/maintenance/prune-telemetry`, and prompts/runs/audit history at `/api/v1/admin/maintenance/prune-operational-history`. Configure `TELEMETRY_RETENTION_DAYS`, `AGENT_RUN_RETENTION_DAYS`, and `AUDIT_RETENTION_DAYS` to match policy.

## Backup and recovery

Back up MongoDB daily using `mongodump` and retain a tested restore point. Back up the MinIO `newsforge-media` bucket with versioning or a replication target. Restore MongoDB first, then media, validate `/api/v1/health`, and run the demo reset only in non-production environments. Monitor backend health, MongoDB health, MinIO health, failed agent runs, agent cost metrics, and rate-limit rejections.
