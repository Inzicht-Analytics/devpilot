import unittest
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor

from devpilot.approval_gate import ApprovalGate
from devpilot.approvals import ApprovalDenied, Decision
from devpilot.github_read import PILOT_REPOSITORY
from devpilot.orchestrator import create_task, TaskStatus
from devpilot.planning import RepositorySnapshot, prepare_plan


class GateTests(unittest.TestCase):
    def setUp(self):
        self.task, self.plan = prepare_plan(create_task(PILOT_REPOSITORY, "Inspect"),
            RepositorySnapshot(PILOT_REPOSITORY, (), ()))
        self.gate = ApprovalGate("owner", lambda token: {"valid": "owner", "other": "guest"}.get(token))
        self.gate.register(self.task, self.plan)

    def submit(self, token="valid", plan=None, decision=Decision.APPROVE):
        return self.gate.submit(str(self.task.id), plan or self.plan, token, decision, "reviewed")

    def test_owner_only(self):
        for token in ("", "invalid", "other"):
            with self.assertRaises(ApprovalDenied):
                self.submit(token)
        self.assertEqual(self.gate.history(), ())
        task, record = self.submit()
        self.assertEqual(task.status, TaskStatus.AWAITING_APPROVAL)
        self.assertEqual(record.reviewer, "owner")

    def test_changed_proposal_rejected(self):
        with self.assertRaises(ApprovalDenied):
            self.submit(plan=replace(self.plan, proposed_steps=("changed",)))
        self.assertEqual(self.gate.history(), ())
        self.submit()

    def test_replay_and_reregistration_denied(self):
        self.submit()
        with self.assertRaises(ApprovalDenied):
            self.submit()
        with self.assertRaises(ApprovalDenied):
            self.gate.register(self.task, self.plan)
        self.assertEqual(len(self.gate.history()), 1)

    def test_rejection(self):
        task, record = self.submit(decision=Decision.REJECT)
        self.assertEqual(task.status, TaskStatus.CANCELLED)
        self.assertEqual(record.decision, Decision.REJECT)

    def test_verifier_failure(self):
        def fail(token):
            raise RuntimeError("private credential")
        gate = ApprovalGate("owner", fail)
        gate.register(self.task, self.plan)
        with self.assertRaisesRegex(ApprovalDenied, "^identity verification failed$"):
            gate.submit(str(self.task.id), self.plan, "valid", Decision.APPROVE, "ok")
        self.assertEqual(gate.history(), ())

    def test_concurrent_duplicate_decisions(self):
        def attempt(_):
            try:
                self.submit()
                return True
            except ApprovalDenied:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(attempt, range(8))), 1)
        self.assertEqual(len(self.gate.history()), 1)

    def test_unknown_task(self):
        with self.assertRaises(ApprovalDenied):
            self.gate.submit("unknown", self.plan, "valid", Decision.APPROVE, "ok")

    def test_invalid_registration(self):
        with self.assertRaises(ApprovalDenied):
            self.gate.register(self.task, replace(self.plan, repository="other/repo"))
