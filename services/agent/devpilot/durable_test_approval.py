"""Durable owner approval of exact bounded test requests, without execution."""
from contextlib import closing
from dataclasses import fields
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
import sqlite3
from uuid import uuid4

from .owner_auth import OwnerAuth
from .sandbox import SandboxRequest, SandboxOperation, validate_request


class TestApprovalDenied(ValueError):
    pass


class DurableTestApproval:
    """Host-only SQLite approval ledger. Never issues grants or runs tests."""

    def __init__(self, path, auth: OwnerAuth, owner: str):
        if type(auth) is not OwnerAuth or type(owner) is not str or not owner.strip():
            raise TestApprovalDenied("trusted owner authentication required")
        self.path, self.auth, self.owner = path, auth, owner
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""CREATE TABLE IF NOT EXISTS test_approvals (
                id TEXT PRIMARY KEY, task TEXT NOT NULL, owner TEXT NOT NULL,
                request_digest TEXT NOT NULL, approved_at TEXT NOT NULL,
                expires_at TEXT NOT NULL, consumed_at TEXT, revoked_at TEXT)""")

    def _connect(self):
        return sqlite3.connect(self.path, timeout=10)

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    def _verify(self, token):
        if self.auth.verify(token) != self.owner:
            raise TestApprovalDenied("owner authentication required")

    @staticmethod
    def _binding(request):
        if type(request) is not SandboxRequest:
            raise TestApprovalDenied("invalid test request")
        validate_request(request)
        if request.operation is not SandboxOperation.RUN_TESTS or request.proposal_digest is not None:
            raise TestApprovalDenied("only unbound RUN_TESTS requests supported")
        payload = {field.name: getattr(request, field.name) for field in fields(SandboxRequest)}
        payload["task_id"] = str(request.task_id)
        payload["operation"] = request.operation.value
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return sha256(encoded).hexdigest()

    def approve(self, request, token, ttl_seconds=300):
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 900:
            raise TestApprovalDenied("invalid approval lifetime")
        digest = self._binding(request)
        self._verify(token)
        approved_at = self._now()
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()
        approval_id = str(uuid4())
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT INTO test_approvals
                (id, task, owner, request_digest, approved_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (approval_id, str(request.task_id), self.owner, digest, approved_at, expires_at))
        return approval_id

    def consume(self, approval_id, request, token):
        """Atomically consume one exact unexpired approval across processes."""
        digest = self._binding(request)
        self._verify(token)
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            result = db.execute("""UPDATE test_approvals SET consumed_at=?
                WHERE id=? AND task=? AND owner=? AND request_digest=?
                AND consumed_at IS NULL AND revoked_at IS NULL AND expires_at > ?""",
                (self._now(), approval_id, str(request.task_id), self.owner, digest, self._now()))
            if result.rowcount != 1:
                raise TestApprovalDenied("approval unavailable or request mismatch")
        return request

    def revoke(self, approval_id, token):
        self._verify(token)
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            result = db.execute("""UPDATE test_approvals SET revoked_at=?
                WHERE id=? AND owner=? AND consumed_at IS NULL AND revoked_at IS NULL""",
                (self._now(), approval_id, self.owner))
            if result.rowcount != 1:
                raise TestApprovalDenied("approval unavailable")

    def history(self, token):
        self._verify(token)
        with closing(self._connect()) as db:
            return tuple(db.execute("""SELECT id, task, owner, request_digest,
                approved_at, expires_at, consumed_at, revoked_at
                FROM test_approvals WHERE owner=? ORDER BY approved_at, id""", (self.owner,)))
