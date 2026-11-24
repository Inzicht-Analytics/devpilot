"""Durable, single-use owner approval for offline code proposals."""
from contextlib import closing
from datetime import datetime, timezone
import sqlite3
from uuid import uuid4

from .owner_auth import OwnerAuth
from .proposal_validation import dry_run_request


class CodeApprovalDenied(ValueError):
    pass


class DurableCodeApproval:
    """Trusted host only; local SQLite storage, never execution authority."""

    def __init__(self, path, auth: OwnerAuth, owner: str):
        if not isinstance(auth, OwnerAuth) or not isinstance(owner, str) or not owner.strip():
            raise CodeApprovalDenied("owner authentication required")
        self.path = path
        self.auth = auth
        self.owner = owner
        with closing(self._connect()) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS code_approvals (
                id TEXT PRIMARY KEY, task TEXT NOT NULL UNIQUE,
                repository TEXT NOT NULL, commit_sha TEXT NOT NULL,
                digest TEXT NOT NULL, owner TEXT NOT NULL,
                approved_at TEXT NOT NULL, consumed_at TEXT)""")

    def _connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def _verify(self, token):
        if self.auth.verify(token) != self.owner:
            raise CodeApprovalDenied("owner authentication required")

    @staticmethod
    def _binding(request):
        return (str(request.task_id), request.repository, request.commit_sha,
                request.proposal_digest)

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    def approve(self, proposal, trusted_commit, token):
        request = dry_run_request(proposal, trusted_commit)
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._verify(token)
            approval_id = str(uuid4())
            try:
                db.execute("INSERT INTO code_approvals VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                           (approval_id, *self._binding(request), self.owner, self._now()))
            except sqlite3.IntegrityError:
                raise CodeApprovalDenied("task already approved") from None
            return approval_id

    def consume(self, approval_id, proposal, trusted_commit, token):
        """Return a bound offline request once; no execution grant is issued."""
        request = dry_run_request(proposal, trusted_commit)
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._verify(token)
            result = db.execute(
                "UPDATE code_approvals SET consumed_at=? WHERE id=? AND task=? "
                "AND repository=? AND commit_sha=? AND digest=? AND owner=? "
                "AND consumed_at IS NULL",
                (self._now(), approval_id, *self._binding(request), self.owner))
            if result.rowcount != 1:
                raise CodeApprovalDenied("approval unavailable or binding mismatch")
            return request

    def history(self, token):
        self._verify(token)
        with closing(self._connect()) as db:
            return tuple(db.execute("SELECT * FROM code_approvals WHERE owner=? ORDER BY approved_at, id",
                                    (self.owner,)))
