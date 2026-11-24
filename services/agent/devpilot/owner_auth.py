"""Local single-owner authentication; no public endpoint or production configuration."""
import hashlib
import hmac
import secrets
import time
from threading import Lock


class AuthenticationDenied(ValueError):
    pass


class OwnerAuth:
    """Trusted host supplies a random 32-byte owner key through secure provisioning.

    Sessions are opaque, process-local and revoked on restart. The owner key
    must never be available to the agent or sandbox. No password login endpoint.
    """

    def __init__(self, subject: str, owner_key: bytes, ttl_seconds: int = 900):
        if not isinstance(subject, str) or not subject.strip():
            raise AuthenticationDenied("invalid owner subject")
        if type(owner_key) is not bytes or len(owner_key) != 32:
            raise AuthenticationDenied("32-byte random owner key required")
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 900:
            raise AuthenticationDenied("invalid session lifetime")
        self._subject = subject
        self._key_digest = hashlib.sha256(owner_key).digest()
        self._ttl = ttl_seconds
        self._sessions: dict[bytes, float] = {}
        self._lock = Lock()

    def _purge(self, now: float):
        for key in tuple(self._sessions):
            if self._sessions[key] <= now:
                del self._sessions[key]

    def login(self, owner_key: bytes) -> str:
        if type(owner_key) is not bytes or len(owner_key) != 32:
            raise AuthenticationDenied("authentication failed")
        if not hmac.compare_digest(hashlib.sha256(owner_key).digest(), self._key_digest):
            raise AuthenticationDenied("authentication failed")
        with self._lock:
            now = time.monotonic()
            self._purge(now)
            if len(self._sessions) >= 16:
                raise AuthenticationDenied("session limit reached")
            token = secrets.token_urlsafe(32)
            self._sessions[hashlib.sha256(token.encode()).digest()] = now + self._ttl
            return token

    def verify(self, token: str) -> str | None:
        if type(token) is not str or len(token) != 43 or not token.isascii():
            return None
        digest = hashlib.sha256(token.encode()).digest()
        with self._lock:
            self._purge(time.monotonic())
            return self._subject if digest in self._sessions else None

    def revoke(self, token: str) -> None:
        if type(token) is not str or len(token) != 43 or not token.isascii():
            return
        with self._lock:
            self._sessions.pop(hashlib.sha256(token.encode()).digest(), None)

    def revoke_all(self) -> None:
        with self._lock:
            self._sessions.clear()
