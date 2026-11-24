import unittest
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
