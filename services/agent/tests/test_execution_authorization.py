import secrets
import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import patch
from uuid import uuid4

from devpilot.owner_auth import OwnerAuth
from devpilot.github_read import PILOT_REPOSITORY
from devpilot.sandbox import SandboxRequest, SandboxOperation, DisabledSandbox, SandboxDenied
from devpilot.execution_authorization import ExecutionAuthorization, AuthorizationDenied, GrantState
from devpilot.durable_test_approval import DurableTestApproval
from devpilot.orchestrator import create_task, TaskStatus, transition
from devpilot.planning import RepositorySnapshot, prepare_plan


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        key = secrets.token_bytes(32)
        self.auth = OwnerAuth("owner", key)
        self.token = self.auth.login(key)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db_path = Path(temp.name) / "tests.sqlite"
        self.store = DurableTestApproval(self.db_path, self.auth, "owner")
        self.ledger = ExecutionAuthorization(self.auth, test_approvals=self.store)
        self.task = create_task(PILOT_REPOSITORY, "Review isolated test request")
        self.task, self.plan = prepare_plan(self.task, RepositorySnapshot(PILOT_REPOSITORY, (), ()))
        self.request = SandboxRequest(self.task.id, PILOT_REPOSITORY, "a" * 40,
                                      SandboxOperation.RUN_TESTS)

    def issue_test(self, ledger=None, token=None, ttl_seconds=60, approval_id=None):
        if approval_id is None:
            approval_id = self.store.approve(self.request, self.token)
        return (ledger or self.ledger).issue(self.request, token or self.token, ttl_seconds,
                                           task=self.task, plan=self.plan,
                                           approval_id=approval_id)

    def test_single_use(self):
        grant = self.issue_test()
        self.assertEqual(self.ledger.consume(grant.id, self.request, self.token).state,
                         GrantState.CONSUMED)
        with self.assertRaises(AuthorizationDenied):
            self.ledger.consume(grant.id, self.request, self.token)
        self.assertEqual(len(self.ledger.history(self.token)), 2)

    def test_generic_grant_rejects_patch_validation_without_approval(self):
        # A missing proposal digest must not bypass the durable approval path.
        unbound_patch = replace(self.request, operation=SandboxOperation.VALIDATE_PATCH)
        with self.assertRaises(AuthorizationDenied):
            self.ledger.issue(unbound_patch, self.token)
        bound_patch = replace(unbound_patch, proposal_digest="a" * 64)
        with self.assertRaises(AuthorizationDenied):
            self.ledger.issue(bound_patch, self.token)
        self.assertEqual(self.ledger.history(self.token), ())

    def test_generic_test_execution_grant_still_requires_owner_and_is_single_use(self):
        grant = self.issue_test()
        self.assertEqual(self.ledger.consume(grant.id, self.request, self.token).state,
                         GrantState.CONSUMED)
        with self.assertRaises(AuthorizationDenied):
            self.ledger.consume(grant.id, self.request, self.token)
        with self.assertRaises(SandboxDenied):
            DisabledSandbox().execute(self.request)

    def test_missing_or_stale_plan_rejected_before_grant_is_recorded(self):
        request = self.request
        variants = (
            (None, None, request),
            (self.task, None, request),
            (None, self.plan, request),
            (self.task, replace(self.plan, title="mismatch"), request),
            (transition(self.task, TaskStatus.PLANNING, "replan"), self.plan, request),
            (self.task, self.plan, replace(request, task_id=uuid4())),
        )
        for task, plan, candidate in variants:
            with self.subTest(task=task, plan=plan, candidate=candidate):
                with self.assertRaises(AuthorizationDenied):
                    self.ledger.issue(candidate, self.token, task=task, plan=plan)
                self.assertEqual(self.ledger.history(self.token), ())
        self.issue_test()

    def test_generic_grant_requires_authenticated_owner(self):
        approval = self.store.approve(self.request, self.token)
        self.auth.revoke(self.token)
        with self.assertRaises(AuthorizationDenied):
            self.issue_test(approval_id=approval)
        self.assertEqual(self.ledger._grants, {})

    def test_test_grant_requires_durable_approval(self):
        with self.assertRaises(AuthorizationDenied):
            self.ledger.issue(self.request, self.token, task=self.task, plan=self.plan)
        missing_store = ExecutionAuthorization(self.auth)
        approval = self.store.approve(self.request, self.token)
        with self.assertRaises(AuthorizationDenied):
            missing_store.issue(self.request, self.token, task=self.task, plan=self.plan,
                                approval_id=approval)
        self.assertIsNone(self.store.history(self.token)[0][6])
        grant = self.issue_test(approval_id=approval)
        self.assertEqual(grant.request, self.request)
        with self.assertRaises(AuthorizationDenied):
            self.issue_test(approval_id=approval)

    def test_modified_request_does_not_spend_approval(self):
        approval = self.store.approve(self.request, self.token)
        for change in ({"commit_sha": "b" * 40}, {"memory_mib": 128},
                       {"timeout_seconds": 30}, {"cpu_count": 2},
                       {"output_bytes": 1024}):
            with self.subTest(change=change):
                modified = replace(self.request, **change)
                with self.assertRaises(AuthorizationDenied):
                    self.ledger.issue(modified, self.token, task=self.task, plan=self.plan,
                                      approval_id=approval)
                self.assertIsNone(self.store.history(self.token)[0][6])
        self.issue_test(approval_id=approval)

    def test_rejected_plan_does_not_spend_test_approval(self):
        approval = self.store.approve(self.request, self.token)
        with self.assertRaises(AuthorizationDenied):
            self.ledger.issue(self.request, self.token, task=self.task,
                              plan=replace(self.plan, title="forged"), approval_id=approval)
        self.assertIsNone(self.store.history(self.token)[0][6])
        self.issue_test(approval_id=approval)

    def test_reused_or_revoked_approval_denied(self):
        approval = self.store.approve(self.request, self.token)
        self.issue_test(approval_id=approval)
        with self.assertRaises(AuthorizationDenied):
            self.issue_test(approval_id=approval)
        revoked = self.store.approve(self.request, self.token)
        self.store.revoke(revoked, self.token)
        with self.assertRaises(AuthorizationDenied):
            self.issue_test(approval_id=revoked)

    def test_binding(self):
        grant = self.issue_test()
        for changes in ({"commit_sha": "b" * 40}, {"task_id": uuid4()},
                        {"operation": SandboxOperation.VALIDATE_PATCH},
                        {"memory_mib": 128}, {"timeout_seconds": 30}):
            with self.assertRaises(AuthorizationDenied):
                self.ledger.consume(grant.id, replace(self.request, **changes), self.token)
        with self.assertRaises(SandboxDenied):
            self.ledger.consume(grant.id, replace(self.request, repository="other/repo"), self.token)

    def test_expiry(self):
        with patch("devpilot.execution_authorization.time.monotonic", return_value=100):
            # Use a separate clock-controlled session because time is shared.
            key = secrets.token_bytes(32)
            auth = OwnerAuth("owner", key)
            token = auth.login(key)
            store = DurableTestApproval(self.db_path, auth, "owner")
            ledger = ExecutionAuthorization(auth, test_approvals=store)
            approval = store.approve(self.request, token)
            grant = self.issue_test(ledger, token, 10, approval_id=approval)
        with patch("devpilot.execution_authorization.time.monotonic", return_value=110):
            with self.assertRaises(AuthorizationDenied):
                ledger.consume(grant.id, self.request, token)
            self.assertEqual(ledger.history(token)[-1].state, GrantState.EXPIRED)

    def test_revocation(self):
        grant = self.issue_test()
        self.ledger.revoke(grant.id, self.token)
        with self.assertRaises(AuthorizationDenied):
            self.ledger.consume(grant.id, self.request, self.token)

    def test_authentication(self):
        grant = self.issue_test()
        additional = self.store.approve(self.request, self.token)
        self.auth.revoke(self.token)
        with self.assertRaises(AuthorizationDenied):
            self.ledger.consume(grant.id, self.request, self.token)
        with self.assertRaises(AuthorizationDenied):
            self.issue_test(approval_id=additional)

    def test_concurrent_consumption(self):
        grant = self.issue_test()
        def attempt(_):
            try:
                self.ledger.consume(grant.id, self.request, self.token)
                return True
            except AuthorizationDenied:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(attempt, range(8))), 1)

    def test_execution_stays_disabled(self):
        grant = self.issue_test()
        self.ledger.consume(grant.id, self.request, self.token)
        with self.assertRaises(SandboxDenied):
            DisabledSandbox().execute(self.request)

    def test_restart_and_invalid_ttl(self):
        grant = self.issue_test()
        with self.assertRaises(AuthorizationDenied):
            ExecutionAuthorization(self.auth).consume(grant.id, self.request, self.token)
        approval = self.store.approve(self.request, self.token)
        for ttl in (0, 301, True):
            with self.assertRaises(AuthorizationDenied):
                self.issue_test(ttl_seconds=ttl, approval_id=approval)
        # Validation failures do not burn the owner approval.
        self.issue_test(approval_id=approval)
