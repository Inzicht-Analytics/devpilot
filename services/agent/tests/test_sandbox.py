import unittest
from dataclasses import replace
from uuid import uuid4

from devpilot.github_read import PILOT_REPOSITORY
from devpilot.sandbox import (
    DisabledSandbox, SandboxDenied, SandboxOperation, SandboxRequest, validate_request,
)
from devpilot.policy import Action, allowed


class SandboxTests(unittest.TestCase):
    def setUp(self):
        self.request = SandboxRequest(uuid4(), PILOT_REPOSITORY, "a" * 40,
                                      SandboxOperation.RUN_TESTS)

    def test_isolation_requirements(self):
        rules = validate_request(self.request)
        self.assertTrue(rules.network_disabled)
        self.assertTrue(rules.non_root)
        self.assertTrue(rules.read_only_root)
        self.assertTrue(rules.ephemeral_workspace)
        self.assertTrue(rules.host_mounts_disabled)
        self.assertTrue(rules.secrets_disabled)

    def test_reject_invalid_identity_and_operation(self):
        for changes in ({"repository": "other/repo"}, {"task_id": "fake"},
                        {"commit_sha": "main"}, {"operation": "shell"},
                        {"commit_sha": "a" * 40 + "\\n"}):
            with self.subTest(changes=changes), self.assertRaises(SandboxDenied):
                validate_request(replace(self.request, **changes))

    def test_reject_resource_overrides(self):
        for changes in ({"timeout_seconds": 121}, {"memory_mib": 513},
                        {"cpu_count": 3}, {"output_bytes": 65537},
                        {"timeout_seconds": True}, {"memory_mib": 0}):
            with self.subTest(changes=changes), self.assertRaises(SandboxDenied):
                validate_request(replace(self.request, **changes))

    def test_valid_requests_still_cannot_execute(self):
        for operation in SandboxOperation:
            with self.assertRaisesRegex(SandboxDenied, "execution disabled"):
                DisabledSandbox().execute(replace(self.request, operation=operation))

    def test_existing_mutation_policy_unchanged(self):
        for action in Action:
            self.assertEqual(allowed(action), action in (Action.READ, Action.PLAN))
