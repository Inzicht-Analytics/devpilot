import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from devpilot.approvals import ApprovalDenied, Decision
from devpilot.github_read import PILOT_REPOSITORY
from devpilot.orchestrator import create_task, TaskStatus
from devpilot.planning import RepositorySnapshot, prepare_plan
from devpilot.persistent_approvals import PersistentApprovalGate


class PersistentGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "test.sqlite"
        schema = Path(__file__).resolve().parents[1] / "migrations" / "001_approval_tasks.sql"
        db = sqlite3.connect(self.path)
        try:
            db.executescript(schema.read_text())
        finally:
            db.close()
        self.task, self.plan = prepare_plan(create_task(PILOT_REPOSITORY, "Inspect"),
            RepositorySnapshot(PILOT_REPOSITORY, (), ()))
        self.gate().register(self.task, self.plan)

    def gate(self):
        return PersistentApprovalGate(self.path, "owner",
            lambda token: "owner" if token == "valid" else None)

    def submit(self, token="valid", plan=None, decision=Decision.APPROVE):
        return self.gate().submit(self.task, plan or self.plan, token, decision, "reviewed")

    def test_restart_and_replay(self):
        task, record = self.submit()
        self.assertEqual(task.status, TaskStatus.AWAITING_APPROVAL)
        self.assertEqual(self.gate().history()[0][2], record.proposal_sha256)
        with self.assertRaises(ApprovalDenied):
            self.submit()
        with self.assertRaises(ApprovalDenied):
            self.gate().register(self.task, self.plan)

    def test_rejection_persisted(self):
        task, _ = self.submit(decision=Decision.REJECT)
        self.assertEqual(task.status, TaskStatus.CANCELLED)
        self.assertEqual(self.gate().history()[0][-1], "cancelled")

    def test_invalid_requests_do_not_consume(self):
        with self.assertRaises(ApprovalDenied):
            self.submit(token="invalid")
        with self.assertRaises(ApprovalDenied):
            self.submit(plan=replace(self.plan, proposed_steps=("changed",)))
        self.assertEqual(self.gate().history(), ())
        self.submit()

    def test_concurrent_connections(self):
        def attempt(_):
            try:
                self.submit()
                return 1
            except ApprovalDenied:
                return 0
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(attempt, range(8))), 1)
        self.assertEqual(len(self.gate().history()), 1)

    def test_unknown_task(self):
        other, plan = prepare_plan(create_task(PILOT_REPOSITORY, "Other"),
            RepositorySnapshot(PILOT_REPOSITORY, (), ()))
        with self.assertRaises(ApprovalDenied):
            self.gate().submit(other, plan, "valid", Decision.APPROVE, "ok")
