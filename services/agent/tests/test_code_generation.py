import unittest
from dataclasses import replace
from uuid import uuid4
from devpilot.github_read import PILOT_REPOSITORY
from devpilot.code_generation import (
    SourceFile, GenerationRequest, CodeChange, ProposalDenied, generate,
)


class FakeModel:
    def __init__(self, changes):
        self.changes = changes
        self.calls = 0

    def propose(self, request):
        self.calls += 1
        return self.changes


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.path = "src/components/Card.tsx"
        self.request = GenerationRequest(uuid4(), PILOT_REPOSITORY, "a" * 40,
                                         "Improve card", (SourceFile(self.path, "old"),))
        self.model = FakeModel((CodeChange(self.path, "new"),))

    def test_valid_proposal(self):
        proposal = generate(self.request, self.model)
        self.assertEqual(proposal.request, self.request)
        self.assertEqual(proposal.changes, self.model.changes)
        self.assertEqual(self.request.sources[0].content, "old")

    def test_invalid_request_never_calls_model(self):
        for changes in ({"repository": "other/repo"}, {"commit_sha": "main"},
                        {"instruction": " "}, {"sources": ()},
                        {"sources": (SourceFile(".env", "secret"),)}):
            with self.assertRaises(ProposalDenied):
                generate(replace(self.request, **changes), self.model)
        self.assertEqual(self.model.calls, 0)

    def test_path_restrictions(self):
        for path in ("../Card.tsx", "src/components/../Card.tsx", ".github/workflows/ci.yml",
                     "src/components/New.tsx", "package.json", "src/components/Card.tsx/"):
            with self.assertRaises(ProposalDenied):
                generate(self.request, FakeModel((CodeChange(path, "new"),)))

    def test_invalid_output(self):
        for changes in ([], (), (CodeChange(self.path, ""),),
                        (CodeChange(self.path, "old"),),
                        (CodeChange(self.path, "x" * 16385),),
                        (CodeChange(self.path, "é" * 9000),),
                        (CodeChange(self.path, "a\x00b"),), ("bad",)):
            with self.assertRaises(ProposalDenied):
                generate(self.request, FakeModel(changes))

    def test_duplicate_paths(self):
        source = self.request.sources[0]
        with self.assertRaises(ProposalDenied):
            generate(replace(self.request, sources=(source, source)), self.model)
        request = replace(self.request, sources=(source, SourceFile("src/pages/Home.tsx", "old")))
        with self.assertRaises(ProposalDenied):
            generate(request, FakeModel((CodeChange(self.path, "new"),) * 2))

    def test_total_budget(self):
        sources = tuple(SourceFile(f"src/pages/P{i}.tsx", "old") for i in range(3))
        request = replace(self.request, sources=sources)
        with self.assertRaises(ProposalDenied):
            generate(request, FakeModel(tuple(CodeChange(s.path, "x" * 12000) for s in sources)))
        with self.assertRaises(ProposalDenied):
            generate(replace(request, sources=tuple(SourceFile(s.path, "x" * 12000)
                                                     for s in sources)), self.model)
