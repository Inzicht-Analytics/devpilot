import secrets
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from devpilot.code_generation import CodeProposal, CodeChange, GenerationRequest, SourceFile, ProposalDenied
from devpilot.github_read import PILOT_REPOSITORY
from devpilot.owner_auth import OwnerAuth
from devpilot.durable_code_approval import DurableCodeApproval, CodeApprovalDenied
from devpilot.sandbox import DisabledSandbox, SandboxDenied


class DurableCodeApprovalTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "approval.db"
        key = secrets.token_bytes(32)
        self.auth = OwnerAuth("owner", key)
        self.token = self.auth.login(key)
        self.store = DurableCodeApproval(self.path, self.auth, "owner")
        self.sha = "a" * 40
        path = "src/pages/Home.tsx"
        self.proposal = CodeProposal(GenerationRequest(uuid4(), PILOT_REPOSITORY,
            self.sha, "update", (SourceFile(path, "old"),)), (CodeChange(path, "new"),))

    def approve(self):
        return self.store.approve(self.proposal, self.sha, self.token)

    def test_restart_and_replay(self):
        approval = self.approve()
        store = DurableCodeApproval(self.path, self.auth, "owner")
        request = store.consume(approval, self.proposal, self.sha, self.token)
        with self.assertRaises(CodeApprovalDenied):
            store.consume(approval, self.proposal, self.sha, self.token)
        self.assertIsNotNone(store.history(self.token)[0][-1])
        with self.assertRaises(SandboxDenied):
            DisabledSandbox().execute(request)

    def test_modified_and_stale(self):
        approval = self.approve()
        changed = replace(self.proposal, changes=(replace(self.proposal.changes[0], replacement="other"),))
        with self.assertRaises(CodeApprovalDenied):
            self.store.consume(approval, changed, self.sha, self.token)
        with self.assertRaises(ProposalDenied):
            self.store.consume(approval, self.proposal, "b" * 40, self.token)
        self.store.consume(approval, self.proposal, self.sha, self.token)

    def test_duplicate(self):
        self.approve()
        with self.assertRaises(CodeApprovalDenied):
            self.approve()

    def test_revoked_session(self):
        approval = self.approve()
        self.auth.revoke(self.token)
        with self.assertRaises(CodeApprovalDenied):
            self.store.consume(approval, self.proposal, self.sha, self.token)

    def test_concurrent_consumption(self):
        approval = self.approve()
        def attempt(_):
            try:
                self.store.consume(approval, self.proposal, self.sha, self.token)
                return True
            except CodeApprovalDenied:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(attempt, range(8))), 1)

    def test_revoked_approval(self):
        approval = self.approve()
        self.store.revoke(approval, self.token)
        with self.assertRaises(CodeApprovalDenied):
            self.store.consume(approval, self.proposal, self.sha, self.token)

    def test_expired_approval(self):
        from unittest.mock import patch
        approval = self.approve()
        with patch.object(self.store, "_now", return_value="9999-01-01T00:00:00+00:00"):
            with self.assertRaises(CodeApprovalDenied):
                self.store.consume(approval, self.proposal, self.sha, self.token)
