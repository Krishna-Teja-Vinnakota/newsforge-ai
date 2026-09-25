from datetime import UTC, datetime

import pytest
from bson import ObjectId

from app.core.security import create_access_token
from app.models.user import AdminUserCreateRequest, UserRole
from app.services.users import deactivate_legacy_role_users


async def make_user(db, role: str, *, active: bool = True) -> tuple[dict, dict[str, str]]:
    now = datetime.now(UTC)
    user = {
        "_id": ObjectId(),
        "email": f"{role}-{ObjectId()}@test.newsforge",
        "display_name": role.title(),
        "role": role,
        "is_active": active,
        "password_hash": "unused",
        "avatar_media_id": None,
        "created_at": now,
        "updated_at": now,
    }
    await db.users.insert_one(user)
    headers = {"Authorization": f"Bearer {create_access_token(str(user['_id']), role)}"}
    return user, headers


def test_only_admin_and_editor_are_valid_roles():
    assert {role.value for role in UserRole} == {"admin", "editor"}
    assert AdminUserCreateRequest(
        email="new-user@test.newsforge",
        password="long-enough-password",
        display_name="New User",
    ).role == UserRole.EDITOR


@pytest.mark.asyncio
async def test_legacy_roles_are_converted_to_inactive_editors(db):
    reporter, _ = await make_user(db, "reporter")
    audience, _ = await make_user(db, "audience")
    editor, _ = await make_user(db, "editor")

    assert await deactivate_legacy_role_users() == 2

    for legacy_user in (reporter, audience):
        migrated = await db.users.find_one({"_id": legacy_user["_id"]})
        assert migrated["role"] == "editor"
        assert migrated["is_active"] is False
    unchanged = await db.users.find_one({"_id": editor["_id"]})
    assert unchanged["role"] == "editor"
    assert unchanged["is_active"] is True


@pytest.mark.asyncio
async def test_editor_has_settings_access_but_not_user_management(client, db):
    _, headers = await make_user(db, "editor")

    topic = await client.post(
        "/api/v1/topics",
        headers=headers,
        json={"name": "Investigations", "slug": "investigations"},
    )
    assert topic.status_code == 201, topic.text
    assert (await client.get("/api/v1/users", headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_admin_cannot_create_removed_role(client, admin_headers):
    response = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": "legacy-role@test.newsforge",
            "password": "long-enough-password",
            "display_name": "Legacy Role",
            "role": "reporter",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_legacy_role_token_is_rejected(client, db):
    _, headers = await make_user(db, "reporter")
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401


@pytest.mark.asyncio
async def test_public_registration_is_not_available(client):
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "self@test.newsforge", "password": "long-enough-password", "display_name": "Self Signup"},
    )
    assert response.status_code == 404
