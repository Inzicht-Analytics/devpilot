import secrets
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from devpilot.durable_test_approval import DurableTestApproval, TestApprovalDenied
from devpilot.github_read import PILOT_REPOSITORY
from devpilot.owner_auth import OwnerAuth
from devpilot.sandbox import SandboxRequest, SandboxOperation, DisabledSandbox, SandboxDenied


class DurableTestApprovalTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "approvals.sqlite"
        key = secrets.token_bytes(32)
        self.auth = OwnerAuth("owner", key)
        self.token = self.auth.login(key)
        self.store = DurableTestApproval(self.path, self.auth, "owner")
        self.request = SandboxRequest(uuid4(), PILOT_REPOSITORY, "a" * 40,
                                      SandboxOperation.RUN_TESTS)

    def test_persistent_single_use_and_disabled_execution(self):
        approval = self.store.approve(self.request, self.token)
        restarted = DurableTestApproval(self.path, self.auth, "owner")
        self.assertEqual(restarted.consume(approval, self.request, self.token), self.request)
        with self.assertRaises(TestApprovalDenied):
            restarted.consume(approval, self.request, self.token)
        with self.assertRaises(SandboxDenied):
            DisabledSandbox().execute(self.request)

    def test_exact_request_including_limits_and_commit(self):
        approval = self.store.approve(self.request, self.token)
        for changed in (
            replace(self.request, task_id=uuid4()),
            replace(self.request, commit_sha="b" * 40),
            replace(self.request, timeout_seconds=30),
            replace(self.request, memory_mib=128),
            replace(self.request, cpu_count=2),
            replace(self.request, output_bytes=1024),
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(TestApprovalDenied):
                    self.store.consume(approval, changed, self.token)
        self.assertEqual(self.store.consume(approval, self.request, self.token), self.request)

    def test_non_test_or_bound_request_denied(self):
        for request in (
            replace(self.request, operation=SandboxOperation.VALIDATE_PATCH),
            replace(self.request, proposal_digest="a" * 64),
        ):
            with self.assertRaises(TestApprovalDenied):
                self.store.approve(request, self.token)
        self.assertEqual(self.store.history(self.token), ())

    def test_expiry_and_revocation(self):
        expired = self.store.approve(self.request, self.token)
        with patch.object(self.store, "_now", return_value="9999-01-01T00:00:00+00:00"):
            with self.assertRaises(TestApprovalDenied):
                self.store.consume(expired, self.request, self.token)
        revoked = self.store.approve(self.request, self.token)
        self.store.revoke(revoked, self.token)
        with self.assertRaises(TestApprovalDenied):
            self.store.consume(revoked, self.request, self.token)

    def test_revoked_session_denied(self):
        approval = self.store.approve(self.request, self.token)
        self.auth.revoke(self.token)
        with self.assertRaises(TestApprovalDenied):
            self.store.consume(approval, self.request, self.token)
        with self.assertRaises(TestApprovalDenied):
            self.store.approve(self.request, self.token)

    def test_concurrent_consumption_single_winner(self):
        approval = self.store.approve(self.request, self.token)
        def attempt(_):
            try:
                self.store.consume(approval, self.request, self.token)
                return True
            except TestApprovalDenied:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(attempt, range(8))), 1)

    def test_invalid_ttl(self):
        for ttl in (0, 901, True, 1.5):
            with self.assertRaises(TestApprovalDenied):
                self.store.approve(self.request, self.token, ttl_seconds=ttl)
