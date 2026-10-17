from __future__ import annotations

import hashlib
import hmac
import time
from collections import defaultdict, deque

from fastapi import Depends, Header, HTTPException, Request

from ..config import get_settings

_hits: dict[str, deque] = defaultdict(deque)


def current_owner(authorization: str = Header(default="")) -> str:
    """If DEVPILOT_API_KEY is set, require it as a bearer token. Tasks are scoped to the caller."""
    key = get_settings().api_key
    if not key:
        return "local"
    token = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token, key):
        raise HTTPException(401, "Missing or invalid API key")
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def rate_limit(request: Request, owner: str = Depends(current_owner)) -> None:
    """Sliding-window limiter (in-memory; use Redis if you run several workers)."""
    limit = get_settings().rate_limit_per_hour
    ident = f"{owner}:{request.client.host if request.client else 'unknown'}"
    now, window = time.monotonic(), _hits[ident]
    while window and now - window[0] > 3600:
        window.popleft()
    if len(window) >= limit:
        raise HTTPException(429, "Rate limit reached. Try again later.")
    window.append(now)
