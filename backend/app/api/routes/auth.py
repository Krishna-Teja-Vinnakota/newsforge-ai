from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.api.dependencies import get_current_user
from app.core.database import get_database
from app.core.security import create_access_token, hash_password, verify_password
from app.core.settings import settings
from app.models.user import AuthResponse, LoginRequest, RegisterRequest, UserProfileUpdate, UserResponse
from app.services.users import new_user_document, user_response

router = APIRouter(prefix="/auth")


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest) -> AuthResponse:
    email = str(payload.email).lower()
    role = "admin" if settings.bootstrap_admin_email and email == settings.bootstrap_admin_email.lower() else "audience"
    document = new_user_document(email, hash_password(payload.password), payload.display_name, role)
    try:
        result = await get_database().users.insert_one(document)
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account already exists for this email") from exc
    document["_id"] = result.inserted_id
    user = user_response(document)
    return AuthResponse(access_token=create_access_token(user.id, user.role), user=user)


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
