import secrets
import unittest
from unittest.mock import patch

from devpilot.owner_auth import OwnerAuth, AuthenticationDenied
from devpilot.approval_gate import ApprovalGate
from devpilot.approvals import ApprovalDenied, Decision
from devpilot.github_read import PILOT_REPOSITORY
from devpilot.orchestrator import create_task, TaskStatus
from devpilot.planning import RepositorySnapshot, prepare_plan


class OwnerAuthTests(unittest.TestCase):
    def setUp(self):
        self.key = secrets.token_bytes(32)
        self.auth = OwnerAuth("owner", self.key, ttl_seconds=60)

    def test_login_and_wrong_key(self):
        with self.assertRaises(AuthenticationDenied):
            self.auth.login(bytes(x ^ 255 for x in self.key))
        token = self.auth.login(self.key)
        self.assertEqual(self.auth.verify(token), "owner")
        self.assertIsNone(self.auth.verify("invalid"))

    def test_expiry(self):
        with patch("devpilot.owner_auth.time.monotonic", return_value=100):
            token = self.auth.login(self.key)
        with patch("devpilot.owner_auth.time.monotonic", return_value=160):
            self.assertIsNone(self.auth.verify(token))

    def test_revocation(self):
        first = self.auth.login(self.key)
        second = self.auth.login(self.key)
        self.auth.revoke(first)
        self.assertIsNone(self.auth.verify(first))
        self.assertEqual(self.auth.verify(second), "owner")
        self.auth.revoke_all()
        self.assertIsNone(self.auth.verify(second))

    def test_restart_invalidates_session(self):
        token = self.auth.login(self.key)
        self.assertIsNone(OwnerAuth("owner", self.key).verify(token))

    def test_session_limit(self):
        for _ in range(16):
            self.auth.login(self.key)
        with self.assertRaises(AuthenticationDenied):
            self.auth.login(self.key)

    def test_invalid_configuration(self):
        for subject, key, ttl in (("", self.key, 60), ("owner", b"short", 60),
                                  ("owner", self.key, 901), ("owner", self.key, True)):
            with self.assertRaises(AuthenticationDenied):
                OwnerAuth(subject, key, ttl)

    def test_approval_gate_integration(self):
        task, plan = prepare_plan(create_task(PILOT_REPOSITORY, "Inspect"),
            RepositorySnapshot(PILOT_REPOSITORY, (), ()))
        gate = ApprovalGate("owner", self.auth.verify)
        gate.register(task, plan)
        token = self.auth.login(self.key)
        self.auth.revoke(token)
        with self.assertRaises(ApprovalDenied):
            gate.submit(str(task.id), plan, token, Decision.APPROVE, "reviewed")
        updated, record = gate.submit(str(task.id), plan, self.auth.login(self.key),
                                      Decision.APPROVE, "reviewed")
        self.assertEqual(updated.status, TaskStatus.AWAITING_APPROVAL)
        self.assertEqual(record.reviewer, "owner")
