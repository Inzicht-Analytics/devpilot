"""Process-local approval gate. No execution authority or live authentication."""
from threading import Lock
from typing import Callable

from .approvals import ApprovalDenied, ApprovalRecord, Decision, decide, proposal_digest
from .github_read import PILOT_REPOSITORY
from .orchestrator import Task, TaskStatus
from .planning import ProposedPlan


class ApprovalGate:
    """Trusted service must register plans and supply a real credential verifier.

    The verifier returns a verified stable subject or None. Never expose register
    to untrusted clients. State is process-local and lost on restart.
    """

    def __init__(self, owner_subject: str, verify: Callable[[str], str | None]):
        if not isinstance(owner_subject, str) or not owner_subject.strip() or not callable(verify):
            raise ApprovalDenied("owner and verifier required")
        self._owner = owner_subject
        self._verify = verify
        self._pending: dict[str, tuple[Task, str]] = {}
        self._records: dict[str, ApprovalRecord] = {}
        self._lock = Lock()

    def register(self, task: Task, proposal: ProposedPlan) -> None:
        if (not isinstance(task, Task) or task.status != TaskStatus.AWAITING_APPROVAL
                or not isinstance(proposal, ProposedPlan)
                or task.repository != PILOT_REPOSITORY
                or proposal.repository != task.repository
                or proposal.task_id != str(task.id) or proposal.title != task.title
                or proposal.requires_approval is not True):
            raise ApprovalDenied("invalid pending proposal")
        key = str(task.id)
        digest = proposal_digest(proposal)
        with self._lock:
            if key in self._pending or key in self._records:
                raise ApprovalDenied("task already registered or decided")
            self._pending[key] = (task, digest)

    def submit(self, task_id: str, proposal: ProposedPlan, credential: str,
               decision: Decision, reason: str) -> tuple[Task, ApprovalRecord]:
        if not isinstance(credential, str) or not credential.strip():
            raise ApprovalDenied("credential required")
        try:
            subject = self._verify(credential)
        except Exception:
            raise ApprovalDenied("identity verification failed") from None
        if not isinstance(subject, str) or subject != self._owner:
            raise ApprovalDenied("owner verification failed")
        if not isinstance(task_id, str):
            raise ApprovalDenied("invalid task identifier")
        with self._lock:
            if task_id in self._records or task_id not in self._pending:
                raise ApprovalDenied("unknown or already decided task")
            task, digest = self._pending[task_id]
            if proposal_digest(proposal) != digest:
                raise ApprovalDenied("proposal changed")
            updated, record = decide(task, proposal, subject, decision, reason)
            self._records[task_id] = record
            del self._pending[task_id]
            return updated, record

    def history(self) -> tuple[ApprovalRecord, ...]:
        """Trusted service only; immutable snapshot, not a public endpoint."""
        with self._lock:
            return tuple(self._records.values())
