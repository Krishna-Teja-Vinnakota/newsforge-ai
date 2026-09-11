from datetime import UTC, datetime

from starlette.middleware.base import BaseHTTPMiddleware

from app.core.database import get_database
from app.core.security import decode_access_token


class AuditMiddleware(BaseHTTPMiddleware):
    """Persist an append-only audit event for every mutating HTTP request."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.method not in {"POST", "PATCH", "PUT", "DELETE"}:
            return response
        user_id, user_role = None, "anonymous"
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            try:
                claims = decode_access_token(authorization[7:])
                user_id, user_role = claims.get("sub"), claims.get("role", "authenticated")
            except Exception:
                pass
        try:
            await get_database().audit_logs.insert_one({
                "timestamp": datetime.now(UTC), "user_id": user_id, "user_role": user_role,
                "action": f"{request.method} {request.url.path}", "endpoint": request.url.path,
                "ip_address": request.client.host if request.client else None, "status_code": response.status_code,
            })
        except Exception:
            # Audit logging must never take down a request during a database outage.
            pass
        return response
