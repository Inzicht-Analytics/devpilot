"""Local SQLite approval storage; no production database integration."""
import sqlite3
from contextlib import closing
from pathlib import Path

from .approvals import ApprovalDenied, Decision, decide, proposal_digest
from .github_read import PILOT_REPOSITORY
from .orchestrator import Task, TaskStatus
from .planning import ProposedPlan


class PersistentApprovalGate:
    """Trusted callers register tasks; verifier must authenticate credentials.

    Each operation opens its own connection. The database must be on trusted
    local storage. No execution authority is granted.
    """

    def __init__(self, path: Path, owner_subject: str, verify):
        if not isinstance(owner_subject, str) or not owner_subject.strip() or not callable(verify):
            raise ApprovalDenied("owner and verifier required")
        self.path = Path(path)
        self.owner = owner_subject
        self.verify = verify

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def register(self, task: Task, proposal: ProposedPlan):
        if (not isinstance(task, Task) or task.status != TaskStatus.AWAITING_APPROVAL
                or not isinstance(proposal, ProposedPlan)
                or task.repository != PILOT_REPOSITORY
                or proposal.repository != task.repository
                or proposal.task_id != str(task.id) or proposal.title != task.title
                or proposal.requires_approval is not True):
            raise ApprovalDenied("invalid pending proposal")
        with closing(self.connect()) as db, db:
            try:
                db.execute("INSERT INTO approval_tasks(task_id, repository, title, digest) VALUES (?, ?, ?, ?)",
                           (str(task.id), task.repository, task.title, proposal_digest(proposal)))
            except sqlite3.IntegrityError:
                raise ApprovalDenied("task already registered") from None

    def submit(self, task: Task, proposal: ProposedPlan, credential: str,
               decision: Decision, reason: str):
        if not isinstance(credential, str) or not credential.strip():
            raise ApprovalDenied("credential required")
        try:
            subject = self.verify(credential)
        except Exception:
            raise ApprovalDenied("identity verification failed") from None
        if not isinstance(subject, str) or subject != self.owner:
            raise ApprovalDenied("owner verification failed")
        if not isinstance(task, Task):
            raise ApprovalDenied("invalid task")
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT repository, title, digest, decision FROM approval_tasks WHERE task_id = ?",
                             (str(task.id),)).fetchone()
            if row is None or row[3] is not None:
                raise ApprovalDenied("unknown or already decided task")
            if row[:3] != (task.repository, task.title, proposal_digest(proposal)):
                raise ApprovalDenied("registered proposal mismatch")
            updated, record = decide(task, proposal, subject, decision, reason)
            db.execute("UPDATE approval_tasks SET decision=?, reviewer=?, reason=?, decided_at=?, resulting_status=? WHERE task_id=?",
                       (record.decision.value, record.reviewer, record.reason,
                        record.occurred_at.isoformat(), updated.status.value, record.task_id))
            return updated, record

    def history(self):
        """Trusted service only: immutable tuples of persisted decision fields."""
        with closing(self.connect()) as db:
            return tuple(db.execute(
                "SELECT task_id, repository, digest, decision, reviewer, reason, decided_at, resulting_status "
                "FROM approval_tasks WHERE decision IS NOT NULL ORDER BY decided_at, task_id"))
