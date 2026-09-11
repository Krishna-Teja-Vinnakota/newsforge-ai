import sys
from pathlib import Path

import pytest_asyncio
from bson import ObjectId
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core import database
from app.core.features import require_ai_feature
from app.core.security import create_access_token
from app.core.settings import settings
from main import app


@pytest_asyncio.fixture
async def db(monkeypatch):
    client = AsyncMongoMockClient()
    monkeypatch.setattr(database, "_client", client)
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(settings, "enable_mock_ai", True)
    yield client[settings.mongodb_database]
    client.close()


@pytest_asyncio.fixture
async def admin_user(db):
    user = {
        "_id": ObjectId(), "email": "admin@test.newsforge", "display_name": "Test Admin",
        "role": "admin", "is_active": True, "password_hash": "unused",
    }
    await db.users.insert_one(user)
    return user


@pytest_asyncio.fixture
async def admin_headers(admin_user):
    return {"Authorization": f"Bearer {create_access_token(str(admin_user['_id']), 'admin')}"}


@pytest_asyncio.fixture
async def client(db):
    app.dependency_overrides[require_ai_feature] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()
