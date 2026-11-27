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
from devpilot.github_read import PILOT_REPOSITORY, GitHubReadAdapter
from devpilot.source_verification import SourceVerifier
from unittest.mock import patch
from devpilot.proposal_validation import dry_run_request
from devpilot.sandbox import DisabledSandbox, SandboxDenied
from devpilot.orchestrator import create_task, TaskStatus, transition
from devpilot.planning import RepositorySnapshot, prepare_plan


class ProposalValidationTests(unittest.TestCase):
    def setUp(self):
        self.sha = "a" * 40
        self.path = "src/pages/Home.tsx"
        self.task = create_task(PILOT_REPOSITORY, "Reviewed code change")
        self.task, self.plan = prepare_plan(self.task, RepositorySnapshot(PILOT_REPOSITORY, (), ()))
        self.request = GenerationRequest(self.task.id, PILOT_REPOSITORY, self.sha,
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
        verifier = SourceVerifier(GitHubReadAdapter('test'))
        ledger = ExecutionAuthorization(auth, store, verifier)
        with self.assertRaises(AuthorizationDenied):
            ledger.issue(dry_run_request(self.proposal, self.sha), token)
        approval = store.approve(self.proposal, self.sha, token)
        with patch.object(verifier._reader, 'read_source', return_value='old'):
            grant = authorize_dry_run(ledger, self.proposal, self.sha, token, approval_id=approval, task=self.task, plan=self.plan)
        with patch.object(verifier._reader, 'read_source', return_value='old'):
            with self.assertRaises(CodeApprovalDenied):
                authorize_dry_run(ledger, self.proposal, self.sha, token, approval_id=approval, task=self.task, plan=self.plan)
        changed = replace(self.proposal, changes=(CodeChange(self.path, "modified"),))
        with self.assertRaises(AuthorizationDenied):
            consume_dry_run(ledger, grant.id, changed, self.sha, token)
        with self.assertRaises(ProposalDenied):
            consume_dry_run(ledger, grant.id, self.proposal, "b" * 40, token)
        self.assertEqual(consume_dry_run(ledger, grant.id, self.proposal,
                                        self.sha, token).state, GrantState.CONSUMED)
        with self.assertRaises(AuthorizationDenied):
            consume_dry_run(ledger, grant.id, self.proposal, self.sha, token)

    def test_source_mismatch_does_not_consume_durable_approval(self):
        key = secrets.token_bytes(32)
        auth = OwnerAuth("owner", key)
        token = auth.login(key)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DurableCodeApproval(Path(tmp.name) / "approval.db", auth, "owner")
        verifier = SourceVerifier(GitHubReadAdapter("test"))
        ledger = ExecutionAuthorization(auth, store, verifier)
        approval = store.approve(self.proposal, self.sha, token)
        with patch.object(verifier._reader, "read_source", return_value="forged"):
            with self.assertRaises(AuthorizationDenied):
                authorize_dry_run(ledger, self.proposal, self.sha, token, approval_id=approval, task=self.task, plan=self.plan)
        self.assertIsNone(store.history(token)[0][-1], "approval should remain unused")
        with patch.object(verifier._reader, "read_source", return_value="old"):
            grant = authorize_dry_run(ledger, self.proposal, self.sha, token, approval_id=approval, task=self.task, plan=self.plan)
        self.assertEqual(grant.request.commit_sha, self.sha)

    def test_missing_verifier_fails_closed_before_approval_consumption(self):
        key = secrets.token_bytes(32)
        auth = OwnerAuth("owner", key)
        token = auth.login(key)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DurableCodeApproval(Path(tmp.name) / "approval.db", auth, "owner")
        approval = store.approve(self.proposal, self.sha, token)
        with self.assertRaises(AuthorizationDenied):
            authorize_dry_run(ExecutionAuthorization(auth, store), self.proposal,
                              self.sha, token, approval_id=approval, task=self.task, plan=self.plan)
        self.assertIsNone(store.history(token)[0][-1])

    def test_missing_or_changed_plan_cannot_consume_approval(self):
        key = secrets.token_bytes(32)
        auth = OwnerAuth("owner", key)
        token = auth.login(key)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DurableCodeApproval(Path(tmp.name) / "approval.db", auth, "owner")
        verifier = SourceVerifier(GitHubReadAdapter("test"))
        ledger = ExecutionAuthorization(auth, store, verifier)
        approval = store.approve(self.proposal, self.sha, token)
        variants = (
            (None, None),
            (self.task, None),
            (None, self.plan),
            (self.task, replace(self.plan, title="forged")),
            (transition(self.task, TaskStatus.PLANNING, "replan"), self.plan),
        )
        for task, plan in variants:
            with self.subTest(task=task, plan=plan):
                with self.assertRaises(AuthorizationDenied):
                    authorize_dry_run(ledger, self.proposal, self.sha, token,
                                      approval_id=approval, task=task, plan=plan)
                self.assertIsNone(store.history(token)[0][-1])
        with patch.object(verifier._reader, 'read_source', return_value='old'):
            grant = authorize_dry_run(ledger, self.proposal, self.sha, token,
                                      approval_id=approval, task=self.task, plan=self.plan)
        self.assertEqual(grant.request.task_id, self.task.id)

    def test_revoked_session_cannot_consume(self):
        key = secrets.token_bytes(32)
        auth = OwnerAuth("owner", key)
        token = auth.login(key)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DurableCodeApproval(Path(tmp.name) / "approval.db", auth, "owner")
        verifier = SourceVerifier(GitHubReadAdapter('test'))
        ledger = ExecutionAuthorization(auth, store, verifier)
        with self.assertRaises(AuthorizationDenied):
            ledger.issue(dry_run_request(self.proposal, self.sha), token)
        approval = store.approve(self.proposal, self.sha, token)
        with patch.object(verifier._reader, 'read_source', return_value='old'):
            grant = authorize_dry_run(ledger, self.proposal, self.sha, token, approval_id=approval, task=self.task, plan=self.plan)
        with patch.object(verifier._reader, 'read_source', return_value='old'):
            with self.assertRaises(CodeApprovalDenied):
                authorize_dry_run(ledger, self.proposal, self.sha, token, approval_id=approval, task=self.task, plan=self.plan)
        auth.revoke(token)
        with self.assertRaises(AuthorizationDenied):
            consume_dry_run(ledger, grant.id, self.proposal, self.sha, token)
