from datetime import UTC, datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pymongo.errors import DuplicateKeyError

from app.api.dependencies import require_roles
from app.core.database import get_database
from app.core.security import hash_password
from app.models.user import AdminUserCreateRequest, AdminUserUpdateRequest, UserResponse, UserRole
from app.services.users import new_user_document, user_response

router = APIRouter(prefix="/users")


def _admin(current_user: dict = Depends(require_roles(UserRole.ADMIN))) -> dict:
    return current_user


@router.get("", response_model=list[UserResponse])
async def list_users(_: dict = Depends(_admin), include_inactive: bool = Query(default=True)) -> list[UserResponse]:
    criteria = {} if include_inactive else {"is_active": True}
    cursor = get_database().users.find(criteria).sort("created_at", -1)
    return [user_response(user) async for user in cursor]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(payload: AdminUserCreateRequest, _: dict = Depends(_admin)) -> UserResponse:
    document = new_user_document(str(payload.email), hash_password(payload.password), payload.display_name, payload.role.value)
    try:
        result = await get_database().users.insert_one(document)
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account already exists for this email") from exc
    document["_id"] = result.inserted_id
    return user_response(document)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, payload: AdminUserUpdateRequest, current_admin: dict = Depends(_admin)) -> UserResponse:
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user = await get_database().users.find_one({"_id": ObjectId(user_id)})
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "email" in changes:
        changes["email"] = str(changes["email"]).lower()
    if "password" in changes:
        changes["password_hash"] = hash_password(changes.pop("password"))
    if "role" in changes:
        changes["role"] = changes["role"].value
    if changes.get("is_active") is False and user["_id"] == current_admin["_id"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You cannot deactivate your own account")
    changes["updated_at"] = datetime.now(UTC)
    try:
        await get_database().users.update_one({"_id": user["_id"]}, {"$set": changes})
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account already exists for this email") from exc
    user.update(changes)
    return user_response(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(user_id: str, current_admin: dict = Depends(_admin)) -> Response:
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    target_id = ObjectId(user_id)
    if target_id == current_admin["_id"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You cannot delete your own account")
    result = await get_database().users.update_one({"_id": target_id}, {"$set": {"is_active": False, "updated_at": datetime.now(UTC)}})
    if not result.matched_count:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
