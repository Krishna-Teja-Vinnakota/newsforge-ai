from datetime import UTC, datetime

from bson import ObjectId

from app.models.user import UserResponse


def user_response(user: dict) -> UserResponse:
    return UserResponse(
        id=str(user["_id"]),
        email=user["email"],
        display_name=user["display_name"],
        role=user["role"],
        avatar_media_id=str(user["avatar_media_id"]) if user.get("avatar_media_id") else None,
        is_active=user.get("is_active", True),
        created_at=user["created_at"],
        updated_at=user["updated_at"],
    )


def new_user_document(email: str, password_hash: str, display_name: str, role: str = "audience") -> dict:
    now = datetime.now(UTC)
    return {
        "email": email.lower(),
        "password_hash": password_hash,
        "display_name": display_name.strip(),
        "role": role,
        "avatar_media_id": None,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
