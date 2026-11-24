import unittest
from unittest.mock import patch
from uuid import uuid4
from devpilot.github_read import GitHubReadAdapter, GitHubReadError, PILOT_REPOSITORY
from devpilot.code_generation import GenerationRequest, SourceFile, CodeChange, CodeProposal
from devpilot.source_verification import SourceVerifier, SourceVerificationDenied


class SourceVerificationTests(unittest.TestCase):
    def setUp(self):
        self.sha = "a" * 40
        self.path = "src/pages/Home.tsx"
        self.reader = GitHubReadAdapter("test")
        self.verifier = SourceVerifier(self.reader)
        self.proposal = CodeProposal(GenerationRequest(uuid4(), PILOT_REPOSITORY,
            self.sha, "update", (SourceFile(self.path, "old"),)), (CodeChange(self.path, "new"),))

    def test_exact_source(self):
        with patch.object(self.reader, "read_source", return_value="old") as read:
            self.verifier.verify(self.proposal, self.sha)
            read.assert_called_once_with(self.sha, self.path)

    def test_forged_source(self):
        with patch.object(self.reader, "read_source", return_value="other"):
            with self.assertRaises(SourceVerificationDenied):
                self.verifier.verify(self.proposal, self.sha)

    def test_unavailable(self):
        with patch.object(self.reader, "read_source", side_effect=GitHubReadError()):
            with self.assertRaises(SourceVerificationDenied):
                self.verifier.verify(self.proposal, self.sha)
