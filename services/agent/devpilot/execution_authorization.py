"""Process-local authorization ledger; does not execute code."""
from dataclasses import dataclass, replace
from enum import Enum
from threading import Lock
import time
from uuid import UUID, uuid4

from .owner_auth import OwnerAuth
from .durable_code_approval import DurableCodeApproval
from .sandbox import SandboxRequest, SandboxOperation, validate_request
from .source_verification import SourceVerifier, SourceVerificationDenied
from .plan_linkage import validate_plan_linkage, PlanLinkageDenied


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

    def __init__(self, auth: OwnerAuth, approvals: DurableCodeApproval | None = None,
                 verifier: SourceVerifier | None = None):
        self._auth = auth
        self._approvals = approvals
        self._verifier = verifier
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
        # A generic grant can authorize tests only. Patch validation must be
        # bound to an independently verified proposal and durable approval.
        validate_request(request)
        if request.operation is not SandboxOperation.RUN_TESTS or request.proposal_digest is not None:
            raise AuthorizationDenied("patch validation requires approved proposal")
        return self._issue(request, token, ttl_seconds)

    def issue_proposal(self, approval_id, proposal, trusted_commit, token, ttl_seconds=60, *, task=None, plan=None):
        if type(self._approvals) is not DurableCodeApproval or self._approvals.auth is not self._auth:
            raise AuthorizationDenied("durable approval store required")
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 300:
            raise AuthorizationDenied("invalid grant lifetime")
        # Trusted task/plan identity must be validated before source reads or approval consumption.
        try:
            validate_plan_linkage(task, plan, proposal)
        except PlanLinkageDenied:
            raise AuthorizationDenied('trusted plan linkage required') from None
        # Fail closed: independent pinned-source verification must precede
        # consuming a durable single-use approval.
        if type(self._verifier) is not SourceVerifier:
            raise AuthorizationDenied('independent source verifier required')
        try:
            self._verifier.verify(proposal, trusted_commit)
        except SourceVerificationDenied:
            raise AuthorizationDenied('source verification failed') from None
        request = self._approvals.consume(approval_id, proposal, trusted_commit, token)
        return self._issue(request, token, ttl_seconds)

    def _issue(self, request, token, ttl_seconds):
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
