from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.api.dependencies import get_current_user
from app.core.database import get_database
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import AuthResponse, LoginRequest, UserProfileUpdate, UserResponse
from app.services.users import user_response

router = APIRouter(prefix="/auth")


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest) -> AuthResponse:
    user = await get_database().users.find_one({"email": str(payload.email).lower(), "is_active": True})
    if user is None or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    response = user_response(user)
    return AuthResponse(access_token=create_access_token(response.id, response.role), user=response)


@router.get("/me", response_model=UserResponse)
async def me(current_user: dict = Depends(get_current_user)) -> UserResponse:
    return user_response(current_user)


@router.patch("/me", response_model=UserResponse)
async def update_me(payload: UserProfileUpdate, current_user: dict = Depends(get_current_user)) -> UserResponse:
    changes = {"display_name": payload.display_name.strip(), "updated_at": datetime.now(UTC)}
    if payload.email:
        changes["email"] = str(payload.email).lower()
    if payload.password:
        changes["password_hash"] = hash_password(payload.password)
    try:
        await get_database().users.update_one({"_id": current_user["_id"]}, {"$set": changes})
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account already exists for this email") from exc
    current_user.update(changes)
    return user_response(current_user)
