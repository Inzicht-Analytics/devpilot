import unittest
from dataclasses import replace

from devpilot.approvals import ApprovalDenied, Decision, decide, proposal_digest
from devpilot.github_read import PILOT_REPOSITORY
from devpilot.orchestrator import TaskStatus, create_task
from devpilot.planning import ProposedPlan, RepositorySnapshot, prepare_plan


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.task = create_task(PILOT_REPOSITORY, "Inspect repository")
        self.pending, self.proposal = prepare_plan(
            self.task, RepositorySnapshot(PILOT_REPOSITORY, (), ()))

    def test_approval_is_recorded_without_execution_or_status_change(self):
        held, record = decide(self.pending, self.proposal, "owner", Decision.APPROVE, "Looks good")
        self.assertIs(held, self.pending)
        self.assertEqual(held.status, TaskStatus.AWAITING_APPROVAL)
        self.assertEqual(record.proposal_sha256, proposal_digest(self.proposal))
        self.assertEqual(record.decision, Decision.APPROVE)
        self.assertEqual(len(held.events), 3)

    def test_rejection_cancels_and_audits(self):
        cancelled, record = decide(self.pending, self.proposal, "owner", Decision.REJECT, "Out of scope")
        self.assertEqual(cancelled.status, TaskStatus.CANCELLED)
        self.assertEqual(cancelled.events[-1].to_status, TaskStatus.CANCELLED)
        self.assertEqual(record.decision, Decision.REJECT)
        self.assertEqual(self.pending.status, TaskStatus.AWAITING_APPROVAL)

    def test_rejects_stale_or_wrong_proposal(self):
        for proposal in (
            replace(self.proposal, task_id="wrong"),
            replace(self.proposal, title="changed"),
            replace(self.proposal, repository="other/repo"),
            replace(self.proposal, requires_approval=False),
        ):
            with self.assertRaises(ApprovalDenied):
                decide(self.pending, proposal, "owner", Decision.APPROVE, "ok")

    def test_requires_explicit_identity_reason_and_decision(self):
        for reviewer, decision, reason in (
            ("", Decision.APPROVE, "ok"), ("owner", "approve", "ok"),
            ("owner", Decision.APPROVE, ""), (None, Decision.REJECT, "ok"),
        ):
            with self.assertRaises(ApprovalDenied):
                decide(self.pending, self.proposal, reviewer, decision, reason)

    def test_no_reapproval_of_non_pending_task(self):
        with self.assertRaises(ApprovalDenied):
            decide(self.task, self.proposal, "owner", Decision.APPROVE, "ok")
        cancelled, _ = decide(self.pending, self.proposal, "owner", Decision.REJECT, "no")
        with self.assertRaises(ApprovalDenied):
            decide(cancelled, self.proposal, "owner", Decision.APPROVE, "ok")

    def test_digest_changes_with_proposal_content(self):
        changed = replace(self.proposal, proposed_steps=("Different step",))
        self.assertNotEqual(proposal_digest(changed), proposal_digest(self.proposal))


if __name__ == "__main__":
    unittest.main()
