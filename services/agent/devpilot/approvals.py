"""In-memory owner decisions for read-only proposals; never grants execution rights."""
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json

from .github_read import PILOT_REPOSITORY
from .orchestrator import Task, TaskStatus, transition
from .planning import ProposedPlan


class ApprovalDenied(ValueError):
    """Invalid approval request or inconsistent task/proposal."""


class Decision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


@dataclass(frozen=True)
class ApprovalRecord:
    task_id: str
    repository: str
    proposal_sha256: str
    reviewer: str
    decision: Decision
    reason: str
    occurred_at: datetime


def proposal_digest(proposal: ProposedPlan) -> str:
    """Bind a decision to the exact proposed content, not a mutable title alone."""
    if not isinstance(proposal, ProposedPlan):
        raise ApprovalDenied("invalid proposal")
    payload = [proposal.task_id, proposal.repository, proposal.title,
               list(proposal.observations), list(proposal.proposed_steps),
               proposal.requires_approval]
    return sha256(json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


def decide(task: Task, proposal: ProposedPlan, reviewer: str,
           decision: Decision, reason: str) -> tuple[Task, ApprovalRecord]:
    """Record an explicit human decision; approval leaves the task on hold.

    Rejection cancels the task. Approval never enables code writes or execution.
    The caller must authenticate the reviewer; this function cannot do so.
    """
    if not isinstance(task, Task) or task.status != TaskStatus.AWAITING_APPROVAL:
        raise ApprovalDenied("task is not awaiting approval")
    if not isinstance(proposal, ProposedPlan) or proposal.requires_approval is not True:
        raise ApprovalDenied("proposal must require approval")
    if task.repository != PILOT_REPOSITORY or proposal.repository != task.repository:
        raise ApprovalDenied("repository outside pilot allowlist")
    if proposal.task_id != str(task.id) or proposal.title != task.title:
        raise ApprovalDenied("task/proposal mismatch")
    if not isinstance(decision, Decision):
        raise ApprovalDenied("invalid decision")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ApprovalDenied("authenticated reviewer identifier required")
    if not isinstance(reason, str) or not reason.strip():
        raise ApprovalDenied("decision reason required")
    record = ApprovalRecord(str(task.id), task.repository, proposal_digest(proposal),
                            reviewer.strip(), decision, reason.strip(),
                            datetime.now(timezone.utc))
    if decision == Decision.REJECT:
        return transition(task, TaskStatus.CANCELLED,
                          "proposal rejected by reviewer"), record
    # No transition to COMPLETED or execution state is permitted.
    return task, record
