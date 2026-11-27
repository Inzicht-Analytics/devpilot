import unittest
from dataclasses import replace
from uuid import uuid4

from devpilot.code_generation import CodeProposal, CodeChange, GenerationRequest, SourceFile
from devpilot.github_read import PILOT_REPOSITORY
from devpilot.orchestrator import create_task, TaskStatus, transition
from devpilot.planning import ProposedPlan, RepositorySnapshot, prepare_plan
from devpilot.plan_linkage import PlanLinkageDenied, validate_plan_linkage


class PlanLinkageTests(unittest.TestCase):
    def setUp(self):
        self.task = create_task(PILOT_REPOSITORY, "Update reviewed Career Journey view")
        snapshot = RepositorySnapshot(PILOT_REPOSITORY, (), ())
        self.task, self.plan = prepare_plan(self.task, snapshot)
        self.proposal = CodeProposal(
            GenerationRequest(
                self.task.id, PILOT_REPOSITORY, "a" * 40, "Update reviewed view",
                (SourceFile("src/pages/Home.tsx", "old"),),
            ),
            (CodeChange("src/pages/Home.tsx", "new"),),
        )

    def test_exact_pending_plan_matches_proposal(self):
        self.assertIsNone(validate_plan_linkage(self.task, self.plan, self.proposal))

    def test_rejects_unrelated_task_identity(self):
        changed = replace(self.proposal,
                          request=replace(self.proposal.request, task_id=uuid4()))
        with self.assertRaises(PlanLinkageDenied):
            validate_plan_linkage(self.task, self.plan, changed)

    def test_rejects_proposal_from_other_repository(self):
        changed = replace(self.proposal, request=replace(
            self.proposal.request, repository="attacker/other"))
        with self.assertRaises(PlanLinkageDenied):
            validate_plan_linkage(self.task, self.plan, changed)

    def test_rejects_mismatched_or_unapproved_plan(self):
        for plan in (
            replace(self.plan, task_id=str(uuid4())),
            replace(self.plan, repository="attacker/other"),
            replace(self.plan, title="different task"),
            replace(self.plan, requires_approval=False),
        ):
            with self.subTest(plan=plan):
                with self.assertRaises(PlanLinkageDenied):
                    validate_plan_linkage(self.task, plan, self.proposal)

    def test_rejects_task_not_awaiting_approval(self):
        queued = create_task(PILOT_REPOSITORY, "Other task")
        with self.assertRaises(PlanLinkageDenied):
            validate_plan_linkage(queued, self.plan, self.proposal)
        resumed = transition(self.task, TaskStatus.PLANNING, "replanning")
        with self.assertRaises(PlanLinkageDenied):
            validate_plan_linkage(resumed, self.plan, self.proposal)

    def test_rejects_inconsistent_audit_or_untrusted_input(self):
        corrupt = replace(self.task, events=self.task.events[:-1])
        for task, plan, proposal in (
            (corrupt, self.plan, self.proposal),
            (self.task, object(), self.proposal),
            (self.task, self.plan, object()),
        ):
            with self.assertRaises(PlanLinkageDenied):
                validate_plan_linkage(task, plan, proposal)
