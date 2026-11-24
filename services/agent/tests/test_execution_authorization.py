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


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        key = secrets.token_bytes(32)
        self.auth = OwnerAuth("owner", key)
        self.token = self.auth.login(key)
        self.ledger = ExecutionAuthorization(self.auth)
        self.request = SandboxRequest(uuid4(), PILOT_REPOSITORY, "a" * 40,
                                      SandboxOperation.RUN_TESTS)

    def test_single_use(self):
        grant = self.ledger.issue(self.request, self.token)
        self.assertEqual(self.ledger.consume(grant.id, self.request, self.token).state,
                         GrantState.CONSUMED)
        with self.assertRaises(AuthorizationDenied):
            self.ledger.consume(grant.id, self.request, self.token)
        self.assertEqual(len(self.ledger.history(self.token)), 2)

    def test_binding(self):
        grant = self.ledger.issue(self.request, self.token)
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
            grant = ledger.issue(self.request, token, 10)
        with patch("devpilot.execution_authorization.time.monotonic", return_value=110):
            with self.assertRaises(AuthorizationDenied):
                ledger.consume(grant.id, self.request, token)
            self.assertEqual(ledger.history(token)[-1].state, GrantState.EXPIRED)

    def test_revocation(self):
        grant = self.ledger.issue(self.request, self.token)
        self.ledger.revoke(grant.id, self.token)
        with self.assertRaises(AuthorizationDenied):
            self.ledger.consume(grant.id, self.request, self.token)

    def test_authentication(self):
        grant = self.ledger.issue(self.request, self.token)
        self.auth.revoke(self.token)
        with self.assertRaises(AuthorizationDenied):
            self.ledger.consume(grant.id, self.request, self.token)
        with self.assertRaises(AuthorizationDenied):
            self.ledger.issue(self.request, self.token)

    def test_concurrent_consumption(self):
        grant = self.ledger.issue(self.request, self.token)
        def attempt(_):
            try:
                self.ledger.consume(grant.id, self.request, self.token)
                return True
            except AuthorizationDenied:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(attempt, range(8))), 1)

    def test_execution_stays_disabled(self):
        grant = self.ledger.issue(self.request, self.token)
        self.ledger.consume(grant.id, self.request, self.token)
        with self.assertRaises(SandboxDenied):
            DisabledSandbox().execute(self.request)

    def test_restart_and_invalid_ttl(self):
        grant = self.ledger.issue(self.request, self.token)
        with self.assertRaises(AuthorizationDenied):
            ExecutionAuthorization(self.auth).consume(grant.id, self.request, self.token)
        for ttl in (0, 301, True):
            with self.assertRaises(AuthorizationDenied):
                self.ledger.issue(self.request, self.token, ttl)
