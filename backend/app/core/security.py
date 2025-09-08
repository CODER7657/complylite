from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import settings


def create_access_token(subject: str, role: str, expires_minutes: Optional[int] = None) -> str:
    expire_in = expires_minutes or settings.access_token_expire_minutes
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expire_in)
    payload = {
        "sub": subject,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
    return token


bearer_scheme = HTTPBearer(auto_error=False)

# Simple in-memory rate limit (per-process). For real prod, use Redis.
_rate_state: dict[str, list[float]] = {}

def rate_limit(request: Request, max_per_minute: int = 60):
    if max_per_minute <= 0:
        return
    now = datetime.now(timezone.utc).timestamp()
    key = request.client.host if request.client else "anonymous"
    bucket = _rate_state.setdefault(key, [])
    window_start = now - 60
    # drop old
    while bucket and bucket[0] < window_start:
        bucket.pop(0)
    if len(bucket) >= max_per_minute:
        raise HTTPException(status_code=429, detail="Too Many Requests")
    bucket.append(now)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError as e:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from e


def admin_required(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    if creds is None or not creds.scheme.lower() == "bearer":
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(creds.credentials)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return payload


