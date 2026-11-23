"""Supervised, read-only task planning for the Career Journey pilot.

No execution, PR creation, writes, or authorization is performed here.
"""
from dataclasses import dataclass
from typing import Tuple

from .github_read import GitHubItem, PILOT_REPOSITORY
from .orchestrator import Task, TaskStatus, transition
from .policy import Action, allowed


class PlanningDenied(ValueError):
    """Planning input or policy was rejected."""


@dataclass(frozen=True)
class RepositorySnapshot:
    repository: str
    issues: Tuple[GitHubItem, ...]
    pull_requests: Tuple[GitHubItem, ...]


@dataclass(frozen=True)
class ProposedPlan:
    task_id: str
    repository: str
    title: str
    observations: Tuple[str, ...]
    proposed_steps: Tuple[str, ...]
    requires_approval: bool = True


def gather_snapshot(adapter) -> RepositorySnapshot:
    """Read GitHub metadata only; caller supplies the already configured adapter."""
    if not allowed(Action.READ):
        raise PlanningDenied("read permission denied")
    if getattr(adapter, "repository", None) != PILOT_REPOSITORY:
        raise PlanningDenied("repository outside pilot allowlist")
    issues = adapter.list_issues()
    pulls = adapter.list_pull_requests()
    if not isinstance(issues, tuple) or not isinstance(pulls, tuple):
        raise PlanningDenied("invalid adapter result")
    if len(issues) > 30 or len(pulls) > 30:
        raise PlanningDenied("snapshot exceeds bounded scope")
    if not all(isinstance(x, GitHubItem) for x in issues + pulls):
        raise PlanningDenied("invalid GitHub item")
    return RepositorySnapshot(PILOT_REPOSITORY, issues, pulls)


def prepare_plan(task: Task, snapshot: RepositorySnapshot) -> tuple[Task, ProposedPlan]:
    """Build a deterministic proposal; never treat GitHub titles as instructions."""
    if not allowed(Action.PLAN):
        raise PlanningDenied("planning permission denied")
    if not isinstance(task, Task) or task.status != TaskStatus.QUEUED:
        raise PlanningDenied("task must be queued")
    if not isinstance(snapshot, RepositorySnapshot):
        raise PlanningDenied("invalid snapshot")
    if task.repository != PILOT_REPOSITORY or snapshot.repository != task.repository:
        raise PlanningDenied("repository mismatch")
    if not isinstance(snapshot.issues, tuple) or not isinstance(snapshot.pull_requests, tuple):
        raise PlanningDenied("invalid snapshot collections")
    if not all(isinstance(x, GitHubItem) for x in snapshot.issues + snapshot.pull_requests):
        raise PlanningDenied("invalid snapshot items")
    if len(snapshot.issues) > 30 or len(snapshot.pull_requests) > 30:
        raise PlanningDenied("snapshot exceeds bounded scope")
    planning = transition(task, TaskStatus.PLANNING, "read-only planning started")
    # Metadata is represented only as counts, not executable instructions or commands.
    proposal = ProposedPlan(
        task_id=str(task.id), repository=task.repository, title=task.title,
        observations=(
            f"Open issues inspected: {len(snapshot.issues)} (first page only)",
            f"Open pull requests inspected: {len(snapshot.pull_requests)} (first page only)",
        ),
        proposed_steps=(
            "Review the captured repository metadata with the owner",
            "Define a scoped change and its acceptance criteria",
            "Request explicit approval before any mutating action",
        ),
    )
    pending = transition(planning, TaskStatus.AWAITING_APPROVAL,
                         "read-only proposal prepared; awaiting owner approval")
    return pending, proposal
