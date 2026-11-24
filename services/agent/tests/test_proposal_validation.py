import unittest
import secrets
import tempfile
from pathlib import Path
from devpilot.durable_code_approval import DurableCodeApproval, CodeApprovalDenied
from devpilot.owner_auth import OwnerAuth
from devpilot.execution_authorization import ExecutionAuthorization, AuthorizationDenied, GrantState
from devpilot.proposal_validation import authorize_dry_run, consume_dry_run
from dataclasses import replace
from uuid import uuid4

from devpilot.code_generation import (CodeProposal, CodeChange, GenerationRequest,
                                      SourceFile, ProposalDenied)
from devpilot.github_read import PILOT_REPOSITORY
from devpilot.proposal_validation import dry_run_request
from devpilot.sandbox import DisabledSandbox, SandboxDenied


class ProposalValidationTests(unittest.TestCase):
    def setUp(self):
        self.sha = "a" * 40
        self.path = "src/pages/Home.tsx"
        self.request = GenerationRequest(uuid4(), PILOT_REPOSITORY, self.sha,
                                         "update", (SourceFile(self.path, "old"),))
        self.proposal = CodeProposal(self.request, (CodeChange(self.path, "new"),))

    def test_stable_digest(self):
        self.assertEqual(dry_run_request(self.proposal, self.sha),
                         dry_run_request(self.proposal, self.sha))

    def test_modified_proposal_changes_binding(self):
        changed = replace(self.proposal, changes=(CodeChange(self.path, "different"),))
        self.assertNotEqual(dry_run_request(self.proposal, self.sha),
                            dry_run_request(changed, self.sha))

    def test_stale_commit(self):
        with self.assertRaises(ProposalDenied):
            dry_run_request(self.proposal, "b" * 40)

    def test_forged_path(self):
        with self.assertRaises(ProposalDenied):
            dry_run_request(replace(self.proposal, changes=(CodeChange("../bad", "x"),)),
                            self.sha)

    def test_execution_still_disabled(self):
        with self.assertRaises(SandboxDenied):
            DisabledSandbox().execute(dry_run_request(self.proposal, self.sha))

    def test_exact_proposal_authorization_and_replay(self):
        key = secrets.token_bytes(32)
        auth = OwnerAuth("owner", key)
        token = auth.login(key)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DurableCodeApproval(Path(tmp.name) / "approval.db", auth, "owner")
        ledger = ExecutionAuthorization(auth, store)
        with self.assertRaises(AuthorizationDenied):
            ledger.issue(dry_run_request(self.proposal, self.sha), token)
        approval = store.approve(self.proposal, self.sha, token)
        grant = authorize_dry_run(ledger, self.proposal, self.sha, token, approval_id=approval)
        with self.assertRaises(CodeApprovalDenied):
            authorize_dry_run(ledger, self.proposal, self.sha, token, approval_id=approval)
        changed = replace(self.proposal, changes=(CodeChange(self.path, "modified"),))
        with self.assertRaises(AuthorizationDenied):
            consume_dry_run(ledger, grant.id, changed, self.sha, token)
        with self.assertRaises(ProposalDenied):
            consume_dry_run(ledger, grant.id, self.proposal, "b" * 40, token)
        self.assertEqual(consume_dry_run(ledger, grant.id, self.proposal,
                                        self.sha, token).state, GrantState.CONSUMED)
        with self.assertRaises(AuthorizationDenied):
            consume_dry_run(ledger, grant.id, self.proposal, self.sha, token)

    def test_revoked_session_cannot_consume(self):
        key = secrets.token_bytes(32)
        auth = OwnerAuth("owner", key)
        token = auth.login(key)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DurableCodeApproval(Path(tmp.name) / "approval.db", auth, "owner")
        ledger = ExecutionAuthorization(auth, store)
        with self.assertRaises(AuthorizationDenied):
            ledger.issue(dry_run_request(self.proposal, self.sha), token)
        approval = store.approve(self.proposal, self.sha, token)
        grant = authorize_dry_run(ledger, self.proposal, self.sha, token, approval_id=approval)
        with self.assertRaises(CodeApprovalDenied):
            authorize_dry_run(ledger, self.proposal, self.sha, token, approval_id=approval)
        auth.revoke(token)
        with self.assertRaises(AuthorizationDenied):
            consume_dry_run(ledger, grant.id, self.proposal, self.sha, token)
