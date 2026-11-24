"""Process-local authorization ledger; does not execute code."""
from dataclasses import dataclass, replace
from enum import Enum
from threading import Lock
import time
from uuid import UUID, uuid4

from .owner_auth import OwnerAuth
from .sandbox import SandboxRequest, validate_request


class AuthorizationDenied(ValueError):
    pass


class GrantState(str, Enum):
    ISSUED = "issued"
    CONSUMED = "consumed"
    REVOKED = "revoked"
    EXPIRED = "expired"


@dataclass(frozen=True)
class Grant:
    id: UUID
    request: SandboxRequest
    owner: str
    expires_at: float
    state: GrantState = GrantState.ISSUED


class ExecutionAuthorization:
    """Trusted host only. Explicit owner authorization of the complete request.

    Restart discards all grants. Consumption is a reference ledger operation,
    not permission to bypass the disabled sandbox or existing policy.
    """

    def __init__(self, auth: OwnerAuth):
        self._auth = auth
        self._lock = Lock()
        self._grants: dict[UUID, Grant] = {}
        self._audit: list[Grant] = []

    def _owner(self, token: str) -> str:
        owner = self._auth.verify(token)
        if owner is None:
            raise AuthorizationDenied("owner authentication required")
        return owner

    def _record(self, grant: Grant) -> Grant:
        self._grants[grant.id] = grant
        self._audit.append(grant)
        return grant

    def issue(self, request: SandboxRequest, token: str, ttl_seconds: int = 60) -> Grant:
        validate_request(request)
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 300:
            raise AuthorizationDenied("invalid grant lifetime")
        with self._lock:
            owner = self._owner(token)
            if len(self._grants) >= 1024:
                raise AuthorizationDenied("ledger capacity reached")
            return self._record(Grant(uuid4(), request, owner, time.monotonic() + ttl_seconds))

    def _active(self, grant_id: UUID, owner: str) -> Grant:
        grant = self._grants.get(grant_id)
        if grant is None or grant.owner != owner or grant.state != GrantState.ISSUED:
            raise AuthorizationDenied("grant unavailable")
        if time.monotonic() >= grant.expires_at:
            self._record(replace(grant, state=GrantState.EXPIRED))
            raise AuthorizationDenied("grant expired")
        return grant

    def consume(self, grant_id: UUID, request: SandboxRequest, token: str) -> Grant:
        validate_request(request)
        with self._lock:
            grant = self._active(grant_id, self._owner(token))
            if grant.request != request:
                raise AuthorizationDenied("request differs from authorized request")
            return self._record(replace(grant, state=GrantState.CONSUMED))

    def revoke(self, grant_id: UUID, token: str) -> Grant:
        with self._lock:
            grant = self._active(grant_id, self._owner(token))
            return self._record(replace(grant, state=GrantState.REVOKED))

    def history(self, token: str) -> tuple[Grant, ...]:
        with self._lock:
            self._owner(token)
            return tuple(self._audit)
