"""Password hashing (argon2id), session tokens, login rate limiting, password policy."""
from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional, Tuple

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()  # argon2id with the library's current recommended parameters
# A real hash of a random password, used to spend the same time when the username does not exist (no user enumeration
# by timing).
_DUMMY_HASH = _hasher.hash(secrets.token_hex(16))

MIN_PASSWORD_LEN = 8
MAX_PASSWORD_LEN = 256


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: Optional[str], password: str) -> bool:
    try:
        return _hasher.verify(stored_hash or _DUMMY_HASH, password) and stored_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_problem(username: str, password: str) -> Optional[str]:
    """Return a human-readable reason the password is not acceptable, or None."""
    if len(password) < MIN_PASSWORD_LEN:
        return f"password must be at least {MIN_PASSWORD_LEN} characters"
    if len(password) > MAX_PASSWORD_LEN:
        return f"password must be at most {MAX_PASSWORD_LEN} characters"
    if password.lower() == username.lower():
        return "password must not equal the username"
    return None


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    """Only hashes of session tokens are stored, so a database leak does not hand out live sessions."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class LoginRateLimiter:
    """After ``max_failures`` failed logins for the same (ip, username) within ``window`` seconds, refuse further
    attempts for ``lockout`` seconds. In-memory: resets on restart (documented limitation)."""

    def __init__(self, max_failures: int, window: float, lockout: float) -> None:
        self.max_failures, self.window, self.lockout = max_failures, window, lockout
        self._fails: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)
        self._locked_until: Dict[Tuple[str, str], float] = {}
        self._lock = threading.Lock()

    def locked_for(self, ip: str, username: str, now: Optional[float] = None) -> float:
        ts = time.time() if now is None else now
        with self._lock:
            until = self._locked_until.get((ip, username.lower()), 0.0)
            return max(0.0, until - ts)

    def failure(self, ip: str, username: str, now: Optional[float] = None) -> None:
        ts = time.time() if now is None else now
        key = (ip, username.lower())
        with self._lock:
            q = self._fails[key]
            q.append(ts)
            while q and ts - q[0] > self.window:
                q.popleft()
            if len(q) >= self.max_failures:
                self._locked_until[key] = ts + self.lockout
                q.clear()

    def success(self, ip: str, username: str) -> None:
        with self._lock:
            self._fails.pop((ip, username.lower()), None)
            self._locked_until.pop((ip, username.lower()), None)
