# Architecture decision: LangGraph workflow orchestration

NewsForge uses LangGraph for the long-running editorial path because it has two explicit human pauses, durable state snapshots, and a visible node trace. Direct route calls remain available for small administrative actions and test setup.

The graph is `intake → selection → human approval → retrieve/draft → editorial review → publish → telemetry → rerank`. Each node calls the established service contract, records a state-history event, and is safe to invoke again where it updates an existing lead or draft.

`MemorySaver` is the default local-development checkpointer. Deployment must use a shared checkpointer implementation backed by MongoDB or Postgres before horizontally scaling the backend. The workflow API also persists the latest state snapshot in `workflow_threads` for audit and recovery visibility.

Node retries are intentionally limited to API-level safe retries today; provider timeouts are recorded as failed agent runs. Production deployment should configure provider retry/backoff centrally and alert on repeated failures.
