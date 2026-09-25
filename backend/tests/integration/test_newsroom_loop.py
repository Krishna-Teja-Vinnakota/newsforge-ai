import pytest


@pytest.mark.asyncio
async def test_newsroom_feedback_loop(client, db, admin_headers):
    reset = await client.post("/api/v1/admin/reset-demo", headers=admin_headers, json={})
    assert reset.status_code == 200
    assert reset.json() == {"status": "success", "seeded_leads": 6, "indexed_sources": 3, "message": "Demo scenario reset successfully."}
    assert await db.lead_inbox.count_documents({}) == 6
    assert await db.editorial_index.count_documents({}) == 3
    assert await db.articles.count_documents({"demo": True}) == 3
    assert await db.users.count_documents({"demo": True}) == 1

    leads = await client.get("/api/v1/agents/leads", headers=admin_headers)
    assert leads.status_code == 200
    target = next(lead for lead in leads.json() if lead["headline"] == "Ohio Tech Corridor Expands with Major Microchip Facility Investment")
    selection_payload = {"leads": [{key: lead[key] for key in ("id", "headline", "topic", "geo")} for lead in leads.json()]}
    first_selection = await client.post("/api/v1/agents/selection/run", headers=admin_headers, json=selection_payload)
    assert first_selection.status_code == 200
    assert sorted(item["current_rank"] for item in first_selection.json()["output"]["ranked"]) == [1, 2, 3, 4, 5, 6]
    before = await db.lead_inbox.find_one({"lead_id": target["id"]})

    production = await client.post("/api/v1/agents/produce", headers=admin_headers, json={"headline": target["headline"], "topic": target["topic"], "context": "<script>unsafe()</script>Ohio manufacturing context.", "source_lead_id": target["id"]})
    assert production.status_code == 200
    article_id = production.json()["output"]["article"]["id"]
    article = await db.articles.find_one({"source_lead_id": target["id"]})
    assert article["_id"] == type(article["_id"])(article_id)
    assert article["retrieved_sources"]
    assert "<script" not in article["content_html"].lower()

    article_path = f"/api/v1/cms/articles/{article_id}"
    assert (await client.post(f"{article_path}/submit-review", headers=admin_headers, json={})).status_code == 200
    assert (await client.post(f"{article_path}/approve", headers=admin_headers, json={})).status_code == 200
    assert (await client.post(f"{article_path}/publish", headers=admin_headers, json={})).status_code == 200

    telemetry = await client.post("/api/v1/telemetry/simulate", headers=admin_headers, json={"topic": "nation-world", "geo": "Ohio", "sample_size": 1000})
    assert telemetry.status_code == 200
    # The lead published above is no longer open for ranking, so the other five are re-ranked.
    assert telemetry.json()["affected_leads_count"] == 5
    second_selection = await client.post("/api/v1/agents/selection/run", headers=admin_headers, json=selection_payload)
    assert second_selection.status_code == 200
    after = await db.lead_inbox.find_one({"lead_id": target["id"]})
    assert after["final_score"] > before["final_score"]
    assert after["learned_weight_delta"] > 0
    assert after["current_rank"] <= before["current_rank"]


@pytest.mark.asyncio
async def test_agent_rate_limit_and_observability_records(client, db, admin_headers):
    await client.post("/api/v1/admin/reset-demo", headers=admin_headers, json={})
    lead = await db.lead_inbox.find_one({})
    payload = {"leads": [{"id": lead["lead_id"], "headline": lead["headline"], "topic": lead["topic"], "geo": lead["geo"]}]}
    responses = [await client.post("/api/v1/agents/selection/run", headers=admin_headers, json=payload) for _ in range(11)]
    assert responses[-1].status_code == 429
    metric = await db.agent_metrics.find_one({"agent": "selection"})
    assert metric and metric["input_tokens"] > 0 and metric["latency_ms"] >= 0
    audit = await db.audit_logs.find_one({"endpoint": "/api/v1/agents/selection/run"})
    assert audit and audit["user_role"] == "admin" and audit["status_code"] == 200
