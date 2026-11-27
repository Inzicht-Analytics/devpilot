import secrets
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import patch
from uuid import uuid4

from devpilot.owner_auth import OwnerAuth
from devpilot.github_read import PILOT_REPOSITORY
from devpilot.sandbox import SandboxRequest, SandboxOperation, DisabledSandbox, SandboxDenied
from devpilot.execution_authorization import ExecutionAuthorization, AuthorizationDenied, GrantState
from devpilot.orchestrator import create_task, TaskStatus, transition
from devpilot.planning import RepositorySnapshot, prepare_plan


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        key = secrets.token_bytes(32)
        self.auth = OwnerAuth("owner", key)
        self.token = self.auth.login(key)
        self.ledger = ExecutionAuthorization(self.auth)
        self.task = create_task(PILOT_REPOSITORY, "Review isolated test request")
        self.task, self.plan = prepare_plan(self.task, RepositorySnapshot(PILOT_REPOSITORY, (), ()))
        self.request = SandboxRequest(self.task.id, PILOT_REPOSITORY, "a" * 40,
                                      SandboxOperation.RUN_TESTS)

    def issue_test(self, ledger=None, token=None, ttl_seconds=60):
        return (ledger or self.ledger).issue(self.request, token or self.token, ttl_seconds,
                                           task=self.task, plan=self.plan)

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
        self.auth.revoke(self.token)
        with self.assertRaises(AuthorizationDenied):
            self.issue_test()
        self.assertEqual(self.ledger._grants, {})

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
            ledger = ExecutionAuthorization(auth)
            grant = self.issue_test(ledger, token, 10)
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
        self.auth.revoke(self.token)
        with self.assertRaises(AuthorizationDenied):
            self.ledger.consume(grant.id, self.request, self.token)
        with self.assertRaises(AuthorizationDenied):
            self.issue_test()

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
        for ttl in (0, 301, True):
            with self.assertRaises(AuthorizationDenied):
                self.issue_test(ttl_seconds=ttl)
