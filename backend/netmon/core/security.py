"""Password hashing, JWT tokens and a small login brute-force guard."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash

from netmon.core.config import Settings

_hasher = PasswordHash.recommended()  # Argon2id


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _hasher.verify(password, hashed)
    except Exception:  # malformed hash -> treat as mismatch
        return False


def create_access_token(
    settings: Settings, subject: str, extra: dict[str, Any] | None = None
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        "type": "access",
        **(extra or {}),
    }
    return jwt.encode(payload, settings.secret_key.get_secret_value(), settings.jwt_algorithm)


class TokenError(Exception):
    pass


def decode_access_token(settings: Settings, token: str) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if payload.get("type") != "access":
        raise TokenError("wrong token type")
    return payload


class LoginThrottle:
    """In-memory sliding-window limiter for failed logins (per client + username).

    Good enough for a single API instance; a multi-instance deployment should move this
    state into Redis or the database.
    """

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._failures[key]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def is_locked(self, key: str) -> bool:
        return len(self._prune(key, time.monotonic())) >= self.max_attempts

    def retry_after(self, key: str) -> int:
        q = self._prune(key, time.monotonic())
        if not q:
            return 0
        return max(1, int(self.window - (time.monotonic() - q[0])))

    def register_failure(self, key: str) -> None:
        now = time.monotonic()
        self._prune(key, now).append(now)

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)
