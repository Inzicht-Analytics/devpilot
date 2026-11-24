"""Durable, single-use owner approval for offline code proposals."""
from contextlib import closing
from datetime import datetime, timezone, timedelta
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
            db.execute("BEGIN IMMEDIATE")
            db.execute("""CREATE TABLE IF NOT EXISTS code_approvals (
                id TEXT PRIMARY KEY, task TEXT NOT NULL UNIQUE,
                repository TEXT NOT NULL, commit_sha TEXT NOT NULL,
                digest TEXT NOT NULL, owner TEXT NOT NULL,
                approved_at TEXT NOT NULL, consumed_at TEXT,
                expires_at TEXT, revoked_at TEXT)""")

            columns = {row[1] for row in db.execute("PRAGMA table_info(code_approvals)")}
            for column in ("expires_at", "revoked_at"):
                if column not in columns:
                    db.execute(f"ALTER TABLE code_approvals ADD COLUMN {column} TEXT")

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

    def approve(self, proposal, trusted_commit, token, ttl_seconds=300):
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 900:
            raise CodeApprovalDenied("invalid approval lifetime")
        request = dry_run_request(proposal, trusted_commit)
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._verify(token)
            approval_id = str(uuid4())
            try:
                db.execute("INSERT INTO code_approvals (id, task, repository, commit_sha, digest, owner, approved_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                           (approval_id, *self._binding(request), self.owner, self._now(), (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()))
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
                "AND consumed_at IS NULL AND revoked_at IS NULL AND expires_at > ?",
                (self._now(), approval_id, *self._binding(request), self.owner, self._now()))
            if result.rowcount != 1:
                raise CodeApprovalDenied("approval unavailable or binding mismatch")
            return request

    def revoke(self, approval_id, token):
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._verify(token)
            result = db.execute("UPDATE code_approvals SET revoked_at=? WHERE id=? AND owner=? AND consumed_at IS NULL AND revoked_at IS NULL",
                                (self._now(), approval_id, self.owner))
            if result.rowcount != 1:
                raise CodeApprovalDenied("approval unavailable")

    def history(self, token):
        self._verify(token)
        with closing(self._connect()) as db:
            return tuple(db.execute("SELECT id, task, repository, commit_sha, digest, owner, approved_at, expires_at, revoked_at, consumed_at FROM code_approvals WHERE owner=? ORDER BY approved_at, id",
                                    (self.owner,)))
