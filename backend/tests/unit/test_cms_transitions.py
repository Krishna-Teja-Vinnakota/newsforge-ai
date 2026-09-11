from datetime import UTC, datetime

import pytest
from bson import ObjectId

from app.models.article import ArticleStatus


@pytest.mark.asyncio
async def test_cms_requires_review_and_approval_before_publish(client, db, admin_headers, admin_user):
    now = datetime.now(UTC)
    article = {"_id": ObjectId(), "slug": "test-transition", "title": "Test transition", "dek": "A test article", "content_json": {}, "content_html": "<p>Copy</p>", "topic": "technology", "tags": [], "status": ArticleStatus.DRAFT, "creator_id": admin_user["_id"], "editor_id": None, "hero_media_id": None, "hero_url": None, "created_at": now, "updated_at": now, "published_at": None, "scheduled_for": None, "metrics": {}}
    await db.articles.insert_one(article)
    article_path = f"/api/v1/cms/articles/{article['_id']}"
    assert (await client.post(f"{article_path}/publish", headers=admin_headers, json={})).status_code == 400
    assert (await client.post(f"{article_path}/submit-review", headers=admin_headers, json={})).json()["status"] == "under_review"
    assert (await client.post(f"{article_path}/approve", headers=admin_headers, json={})).json()["status"] == "approved"
    assert (await client.post(f"{article_path}/publish", headers=admin_headers, json={})).json()["status"] == "published"
