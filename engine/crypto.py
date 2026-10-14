"""HMAC cookie signing for flow rules (pure Python, standard library only).

cookie (64 bit) = (tag48 << 16) | epoch16
tag48          = first 48 bits of HMAC-SHA256(K_epoch, canonical_bytes(dpid, epoch, rule))
K_epoch        = HMAC-SHA256(master_key, b"flowguard-epoch" || epoch16)

Binding dpid and epoch into the signed bytes stops a valid cookie being reused on another switch or after a
key rotation. After ``rotate()`` the previous epoch stays acceptable only for ``grace_seconds``.
Verification is constant time. The master key never leaves this module except through ``Signer``.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import stat
import time
from dataclasses import dataclass
from typing import Dict, Optional

from .canonical import RuleSpec

TAG_BITS = 48
EPOCH_BITS = 16
EPOCH_MASK = (1 << EPOCH_BITS) - 1
MIN_KEY_BYTES = 32
DEFAULT_KEY_ENV = "FLOWGUARD_HMAC_KEY"


class KeyMaterialError(Exception):
    """The HMAC key is missing, malformed or stored insecurely. The engine must refuse to start."""


# ---- key material -------------------------------------------------------------------------------------------
def _parse_hex_key(text: str, origin: str) -> bytes:
    text = text.strip()
    try:
        key = bytes.fromhex(text)
    except ValueError as exc:
        raise KeyMaterialError(f"{origin}: key must be hexadecimal") from exc
    if len(key) < MIN_KEY_BYTES:
        raise KeyMaterialError(f"{origin}: key must be at least {MIN_KEY_BYTES} bytes ({MIN_KEY_BYTES * 2} hex characters)")
    return key


def load_master_key(path: Optional[str] = None, env_var: str = DEFAULT_KEY_ENV) -> bytes:
    """Load the master key from ``env_var`` if set, otherwise from ``path`` (which must be mode 0600, owned by us)."""
    env_val = os.environ.get(env_var)
    if env_val:
        return _parse_hex_key(env_val, f"environment variable {env_var}")
    if not path:
        raise KeyMaterialError(f"no key: set {env_var} or configure a key file")
    p = os.path.expanduser(path)
    try:
        st = os.stat(p)
    except FileNotFoundError as exc:
        raise KeyMaterialError(f"key file {p} not found (create it with `flowguard keygen`)") from exc
    if not stat.S_ISREG(st.st_mode):
        raise KeyMaterialError(f"key file {p} is not a regular file")
    if st.st_mode & 0o077:
        raise KeyMaterialError(f"key file {p} has mode {stat.S_IMODE(st.st_mode):04o}; it must be 0600")
    if hasattr(os, "geteuid") and st.st_uid != os.geteuid():
        raise KeyMaterialError(f"key file {p} is not owned by the current user")
    with open(p, "r", encoding="ascii") as fh:
        return _parse_hex_key(fh.read(), f"key file {p}")


def generate_key_file(path: str) -> str:
    """Create a new random key file (0600, parent 0700). Refuses to overwrite. Returns its fingerprint."""
    p = os.path.expanduser(path)
    os.makedirs(os.path.dirname(p) or ".", mode=0o700, exist_ok=True)
    key = os.urandom(MIN_KEY_BYTES)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as fh:
        fh.write(key.hex() + "\n")
    return key_fingerprint(key)


def key_fingerprint(master: bytes) -> str:
    """Short identifier that is safe to log or show (derived with a separate label; does not reveal the key)."""
    return hmac.new(master, b"flowguard-fingerprint", hashlib.sha256).hexdigest()[:8]


# ---- epochs -------------------------------------------------------------------------------------------------
@dataclass
class EpochPolicy:
    """Which key epochs are acceptable right now."""

    current: int = 1
    previous: Optional[int] = None
    rotated_at: Optional[float] = None
    grace_seconds: float = 300.0

    def __post_init__(self) -> None:
        if not 0 <= self.current <= EPOCH_MASK:
            raise ValueError("epoch out of range")

    def accepts(self, epoch: int, now: float) -> bool:
        if epoch == self.current:
            return True
        if self.previous is not None and epoch == self.previous and self.rotated_at is not None:
            return 0 <= now - self.rotated_at <= self.grace_seconds
        return False

    def rotate(self, now: float) -> int:
        """Start a new epoch; the old one stays valid for ``grace_seconds``. Returns the new epoch."""
        self.previous = self.current
        self.current = (self.current + 1) & EPOCH_MASK
        self.rotated_at = now
        return self.current

    def to_dict(self) -> Dict[str, object]:
        return {"current": self.current, "previous": self.previous, "rotated_at": self.rotated_at,
                "grace_seconds": self.grace_seconds}

    @staticmethod
    def from_dict(d: Dict[str, object], grace_seconds: Optional[float] = None) -> "EpochPolicy":
        return EpochPolicy(int(d["current"]), None if d.get("previous") is None else int(d["previous"]),  # type: ignore[arg-type]
                           None if d.get("rotated_at") is None else float(d["rotated_at"]),  # type: ignore[arg-type]
                           float(grace_seconds if grace_seconds is not None else d.get("grace_seconds", 300.0)))  # type: ignore[arg-type]


@dataclass(frozen=True)
class Verification:
    valid: bool
    reason: str  # ok | zero_cookie | bad_epoch | bad_tag
    epoch: Optional[int] = None


class Signer:
    """Signs rules and verifies cookies for the epochs allowed by ``policy``."""

    def __init__(self, master_key: bytes, policy: Optional[EpochPolicy] = None) -> None:
        if len(master_key) < MIN_KEY_BYTES:
            raise KeyMaterialError("master key too short")
        self._master = bytes(master_key)
        self.policy = policy or EpochPolicy()
        self._epoch_keys: Dict[int, bytes] = {}

    def _epoch_key(self, epoch: int) -> bytes:
        k = self._epoch_keys.get(epoch)
        if k is None:
            k = hmac.new(self._master, b"flowguard-epoch" + epoch.to_bytes(2, "big"), hashlib.sha256).digest()
            self._epoch_keys[epoch] = k
        return k

    def _tag(self, dpid: object, spec: RuleSpec, epoch: int) -> int:
        digest = hmac.new(self._epoch_key(epoch), spec.canonical_bytes(dpid, epoch), hashlib.sha256).digest()
        return int.from_bytes(digest[: TAG_BITS // 8], "big")

    def cookie_for(self, dpid: object, spec: RuleSpec, epoch: Optional[int] = None) -> int:
        ep = self.policy.current if epoch is None else epoch
        return (self._tag(dpid, spec, ep) << EPOCH_BITS) | ep

    def verify(self, dpid: object, spec: RuleSpec, cookie: int, now: Optional[float] = None) -> Verification:
        if cookie == 0:
            return Verification(False, "zero_cookie")
        if not 0 <= cookie < 1 << 64:
            return Verification(False, "bad_tag")
        epoch = cookie & EPOCH_MASK
        if not self.policy.accepts(epoch, time.time() if now is None else now):
            return Verification(False, "bad_epoch", epoch)
        expected = self._tag(dpid, spec, epoch)
        presented = cookie >> EPOCH_BITS
        ok = hmac.compare_digest(expected.to_bytes(6, "big"), presented.to_bytes(6, "big"))
        return Verification(ok, "ok" if ok else "bad_tag", epoch)

    def fingerprint(self) -> str:
        return key_fingerprint(self._master)

    def __repr__(self) -> str:  # never leak key material into logs
        return f"Signer(fingerprint={self.fingerprint()}, epoch={self.policy.current})"
