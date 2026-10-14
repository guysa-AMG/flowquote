"""PIN-based authentication for local network protection (PLAN.md §9, §10)."""
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

security = HTTPBearer(auto_error=False)
ACTIVE_TOKENS: set[str] = set()


def verify_pin(pin: str) -> str:
    """Verifies PIN and returns a newly minted session token."""
    if pin != settings.auth_pin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid PIN")
    token = secrets.token_urlsafe(32)
    ACTIVE_TOKENS.add(token)
    return token


async def require_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
) -> str:
    """Dependency that enforces a valid token."""
    if not credentials or credentials.credentials not in ACTIVE_TOKENS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required or invalid",
        )
    return credentials.credentials
