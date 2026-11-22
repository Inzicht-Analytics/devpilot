"""Pure, in-memory task lifecycle for Milestone 2 Phase 2.1.

No GitHub writes, external calls, database changes, or task execution.
"""
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Tuple
from uuid import UUID, uuid4


class TaskStatus(str, Enum):
    QUEUED = "queued"
    PLANNING = "planning"
    BLOCKED = "blocked"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Deliberately excludes COMPLETED: no execution or approval verification exists yet.
TRANSITIONS = {
    TaskStatus.QUEUED: frozenset({TaskStatus.PLANNING, TaskStatus.CANCELLED}),
    TaskStatus.PLANNING: frozenset({
        TaskStatus.BLOCKED, TaskStatus.AWAITING_APPROVAL,
        TaskStatus.FAILED, TaskStatus.CANCELLED,
    }),
    TaskStatus.BLOCKED: frozenset({TaskStatus.PLANNING, TaskStatus.CANCELLED}),
    TaskStatus.AWAITING_APPROVAL: frozenset({
        TaskStatus.PLANNING, TaskStatus.CANCELLED,
    }),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}


class InvalidTask(ValueError):
    """Task input is missing required information."""


class InvalidTransition(ValueError):
    """Requested transition is not authorized by the lifecycle."""


@dataclass(frozen=True)
class AuditEvent:
    task_id: UUID
    from_status: TaskStatus | None
    to_status: TaskStatus
    reason: str
    occurred_at: datetime


@dataclass(frozen=True)
class Task:
    id: UUID
    repository: str
    title: str
    status: TaskStatus = TaskStatus.QUEUED
    events: Tuple[AuditEvent, ...] = field(default_factory=tuple)


def create_task(repository: str, title: str) -> Task:
    """Validate input and return a queued task with an immutable audit event."""
    if not isinstance(repository, str) or not repository.strip() or (
        repository.strip().count("/") != 1
        or any(not part.strip() for part in repository.strip().split("/"))
    ):
        raise InvalidTask("repository must be a nonempty owner/name")
    if not isinstance(title, str) or not title.strip():
        raise InvalidTask("title must be nonempty")
    task_id = uuid4()
    created = AuditEvent(
        task_id=task_id,
        from_status=None,
        to_status=TaskStatus.QUEUED,
        reason="task created",
        occurred_at=datetime.now(timezone.utc),
    )
    return Task(id=task_id, repository=repository.strip(), title=title.strip(),
                events=(created,))


def transition(task: Task, target: TaskStatus, reason: str) -> Task:
    """Return a new task and audit trail; reject invalid and no-op transitions."""
    if not isinstance(task, Task):
        raise TypeError("task must be a Task")
    if not isinstance(target, TaskStatus) or target not in TRANSITIONS[task.status]:
        raise InvalidTransition(f"{task.status.value} cannot transition to {target!s}")
    if not isinstance(reason, str) or not reason.strip():
        raise InvalidTransition("transition reason is required")
    event = AuditEvent(
        task_id=task.id,
        from_status=task.status,
        to_status=target,
        reason=reason.strip(),
        occurred_at=datetime.now(timezone.utc),
    )
    return replace(task, status=target, events=task.events + (event,))
