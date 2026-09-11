# NewsForge stakeholder demo

Start the local stack, open Studio at `http://localhost:5174`, and sign in as an administrator.

1. **Demo environment reset** — Open AI Editorial Desk and select **↺ Reset Demo Scenario**. Confirm the success notification.
2. **Editorial lead intake** — Inspect the six curated leads. Point out their topics, geographies, baseline scores, and deterministic ranks.
3. **Run Selection Agent** — Run selection for the inbox. Show the editorial guidance and explain that the numeric score audit remains server-controlled.
4. **Lead approval and RAG draft** — Choose *Ohio Tech Corridor Expands with Major Microchip Facility Investment* and select **Approve & draft**. Show the retrieved internal Ohio semiconductor context in the generated result.
5. **Human editorial review and publishing** — In Production Workspace, submit the draft for review, approve it, then publish it. Explain the enforced `draft → under_review → approved → published` lifecycle.
6. **Audience engagement simulation** — Select **⚡ Simulate 1,000 Reader Visits** for Ohio. Show the new positive Ohio ranking signal and telemetry event activity.
7. **Closed-loop re-ranking** — Run selection again. Verify the Ohio lead’s increased final score and green positive geography-weight badge. Optionally start the Workflow Graph to demonstrate its approval and editorial-review pauses.
