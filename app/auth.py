"""PIN-based authentication for local network protection (PLAN.md §9, §10)."""
import secrets

from fastapi import HTTPException, Security, status
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

def require_auth(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    """Dependency that enforces a valid token."""
    if not credentials or credentials.credentials not in ACTIVE_TOKENS:
        # Allow dev override if debug mode
        if settings.debug and not ACTIVE_TOKENS:
            return "dev_token"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required or invalid",
        )
    return credentials.credentials
