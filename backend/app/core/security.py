from datetime import UTC, datetime, timedelta

import jwt
from fastapi import HTTPException, status
from passlib.context import CryptContext

from app.core.settings import settings

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"
DEFAULT_JWT_SECRET = "development-only-change-me"


def uses_development_jwt_secret(value: str | None = None) -> bool:
    """Allow startup validation to reject the known development secret in production."""
    return (value or settings.jwt_secret) == DEFAULT_JWT_SECRET


def hash_password(password: str) -> str:
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Passwords must not exceed 72 UTF-8 bytes.")
    return password_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    if len(password.encode("utf-8")) > 72:
        return False
    return password_context.verify(password, password_hash)


def create_access_token(user_id: str, role: str) -> str:
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_token_minutes)
    return jwt.encode({"sub": user_id, "role": role, "exp": expires_at}, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired access token") from exc
