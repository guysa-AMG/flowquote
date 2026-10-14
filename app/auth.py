"""PIN-based authentication for local network protection (PLAN.md §9, §10)."""
import hashlib
import hmac
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.db import get_db

security = HTTPBearer(auto_error=False)
ACTIVE_TOKENS: set[str] = set()
_PIN_HASH_ITERATIONS = 310_000


def _hash_pin(pin: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, _PIN_HASH_ITERATIONS)
    return f"pbkdf2_sha256${_PIN_HASH_ITERATIONS}${salt.hex()}${digest.hex()}"


def _pin_matches_hash(pin: str, encoded_hash: str) -> bool:
    algorithm, iterations, salt_hex, digest_hex = encoded_hash.split("$", 3)
    if algorithm != "pbkdf2_sha256":
        raise ValueError("Unsupported stored PIN hash algorithm")
    iteration_count = int(iterations)
    if not 100_000 <= iteration_count <= 1_000_000:
        raise ValueError("Stored PIN hash has an unsafe iteration count")
    digest = hashlib.pbkdf2_hmac(
        "sha256", pin.encode(), bytes.fromhex(salt_hex), iteration_count
    )
    return hmac.compare_digest(digest.hex(), digest_hex)


def _configured_pin_matches(pin: str) -> bool:
    return hmac.compare_digest(pin, settings.auth_pin)


def verify_current_pin(pin: str) -> bool:
    """Verify against a persisted PIN, falling back to configured bootstrap PIN."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT pin_hash FROM auth_pin_setting WHERE business_id = ?",
            (settings.default_business_id,),
        ).fetchone()
    if row is None:
        if not settings.auth_pin:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="PIN is not configured; set TALKQUOTE_AUTH_PIN before logging in",
            )
        return _configured_pin_matches(pin)
    return _pin_matches_hash(pin, row["pin_hash"])


def change_pin(current_pin: str, new_pin: str) -> None:
    """Persist a new PIN after verifying the current PIN."""
    if not verify_current_pin(current_pin):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current PIN is incorrect",
        )
    with get_db() as conn:
        conn.execute(
            """INSERT INTO auth_pin_setting (business_id, pin_hash, updated_at)
               VALUES (?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(business_id) DO UPDATE SET
                   pin_hash = excluded.pin_hash,
                   updated_at = CURRENT_TIMESTAMP""",
            (settings.default_business_id, _hash_pin(new_pin)),
        )


def verify_pin(pin: str) -> str:
    """Verifies PIN and returns a newly minted session token."""
    if not verify_current_pin(pin):
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
