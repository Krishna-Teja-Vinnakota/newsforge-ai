from datetime import UTC, datetime

from bson import ObjectId

from app.core.database import get_database
from app.models.user import UserResponse, UserRole

LEGACY_USER_ROLES = ("reporter", "audience")


def user_response(user: dict) -> UserResponse:
    return UserResponse(
        id=str(user["_id"]),
        email=user.get("email", ""),
        display_name=user.get("display_name", ""),
        role=user.get("role", UserRole.EDITOR),
        avatar_media_id=str(user["avatar_media_id"]) if user.get("avatar_media_id") else None,
        is_active=user.get("is_active", True),
        created_at=user.get("created_at"),
        updated_at=user.get("updated_at"),
    )


def new_user_document(
    email: str,
    password_hash: str,
    display_name: str,
    role: UserRole | str = UserRole.EDITOR,
) -> dict:
    now = datetime.now(UTC)
    return {
        "email": email.lower(),
        "password_hash": password_hash,
        "display_name": display_name.strip(),
        "role": role.value if isinstance(role, UserRole) else role,
        "avatar_media_id": None,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }


async def deactivate_legacy_role_users() -> int:
    """Keep legacy accounts visible without silently granting editorial access."""
    result = await get_database().users.update_many(
        {"role": {"$in": list(LEGACY_USER_ROLES)}},
        {
            "$set": {
                "role": UserRole.EDITOR.value,
                "is_active": False,
                "updated_at": datetime.now(UTC),
            }
        },
    )
    return result.modified_count
