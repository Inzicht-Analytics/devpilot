import unittest
from datetime import timezone

from devpilot.orchestrator import (
    InvalidTask, InvalidTransition, TaskStatus, TRANSITIONS,
    create_task, transition,
)


class TestTaskLifecycle(unittest.TestCase):
    def setUp(self):
        self.task = create_task("Inzicht-Analytics/career-journey", "Inspect CI")

    def test_create_queued_task_and_audit(self):
        self.assertEqual(self.task.status, TaskStatus.QUEUED)
        self.assertEqual(len(self.task.events), 1)
        event = self.task.events[0]
        self.assertEqual(event.task_id, self.task.id)
        self.assertIsNone(event.from_status)
        self.assertEqual(event.to_status, TaskStatus.QUEUED)
        self.assertEqual(event.occurred_at.tzinfo, timezone.utc)

    def test_invalid_task_input(self):
        for repository, title in [("", "a"), ("owner", "a"), ("/repo", "a"),
                                  ("owner/", "a"), ("owner/repo", "  ")]:
            with self.subTest(repository=repository, title=title):
                with self.assertRaises(InvalidTask):
                    create_task(repository, title)

    def test_valid_planning_path_and_immutability(self):
        planning = transition(self.task, TaskStatus.PLANNING, "triaged")
        pending = transition(planning, TaskStatus.AWAITING_APPROVAL, "plan ready")
        self.assertEqual(self.task.status, TaskStatus.QUEUED)
        self.assertEqual(len(self.task.events), 1)
        self.assertEqual(pending.status, TaskStatus.AWAITING_APPROVAL)
        self.assertEqual(len(pending.events), 3)
        self.assertEqual(pending.events[-1].from_status, TaskStatus.PLANNING)
        self.assertEqual(pending.events[-1].reason, "plan ready")

    def test_blocked_can_resume_planning(self):
        planning = transition(self.task, TaskStatus.PLANNING, "start")
        blocked = transition(planning, TaskStatus.BLOCKED, "missing details")
        resumed = transition(blocked, TaskStatus.PLANNING, "details received")
        self.assertEqual(resumed.status, TaskStatus.PLANNING)

    def test_terminal_states_are_terminal(self):
        for terminal in (TaskStatus.CANCELLED, TaskStatus.FAILED):
            source = (self.task if terminal == TaskStatus.CANCELLED
                      else transition(self.task, TaskStatus.PLANNING, "start"))
            stopped = transition(source, terminal, "stop")
            for target in TaskStatus:
                with self.subTest(terminal=terminal, target=target):
                    with self.assertRaises(InvalidTransition):
                        transition(stopped, target, "retry")

    def test_no_completion_without_approval_implementation(self):
        for status in (TaskStatus.QUEUED, TaskStatus.PLANNING,
                       TaskStatus.BLOCKED, TaskStatus.AWAITING_APPROVAL):
            self.assertNotIn(TaskStatus.COMPLETED, TRANSITIONS[status])

    def test_all_disallowed_transitions_fail(self):
        reachable = {
            TaskStatus.QUEUED: self.task,
            TaskStatus.PLANNING: transition(self.task, TaskStatus.PLANNING, "start"),
        }
        reachable[TaskStatus.BLOCKED] = transition(
            reachable[TaskStatus.PLANNING], TaskStatus.BLOCKED, "blocked")
        reachable[TaskStatus.AWAITING_APPROVAL] = transition(
            reachable[TaskStatus.PLANNING], TaskStatus.AWAITING_APPROVAL, "review")
        for status, task in reachable.items():
            for target in TaskStatus:
                if target not in TRANSITIONS[status]:
                    with self.subTest(status=status, target=target):
                        with self.assertRaises(InvalidTransition):
                            transition(task, target, "attempt")

    def test_reason_required_and_no_mutation_on_failure(self):
        with self.assertRaises(InvalidTransition):
            transition(self.task, TaskStatus.PLANNING, " ")
        self.assertEqual(len(self.task.events), 1)
        with self.assertRaises(InvalidTransition):
            transition(self.task, TaskStatus.QUEUED, "no-op")
