"""Offline trusted-host linkage of a code proposal to a supervised plan.

This gate validates identities only. It does not approve a plan, consume
an approval, issue a grant, run a sandbox or write to a repository.
"""
from .orchestrator import Task, TaskStatus, AuditEvent, TRANSITIONS
from datetime import datetime, timezone
from uuid import UUID
from .planning import ProposedPlan
from .code_generation import CodeProposal


class PlanLinkageDenied(ValueError):
    """Proposal does not match the trusted task and reviewed plan."""


def _validate_task_history(task: Task) -> None:
    """Check every lifecycle event, not just the last apparent status.

    This establishes internal consistency, not authenticated provenance:
    the trusted host must still supply the task from authoritative storage.
    """
    if (type(task) is not Task or type(task.id) is not UUID
            or type(task.events) is not tuple or len(task.events) < 2
            or type(task.status) is not TaskStatus):
        raise PlanLinkageDenied("trusted task history required")
    previous = None
    last_time = None
    for index, event in enumerate(task.events):
        if (type(event) is not AuditEvent or event.task_id != task.id
                or type(event.to_status) is not TaskStatus
                or type(event.reason) is not str or not event.reason.strip()
                or type(event.occurred_at) is not datetime
                or event.occurred_at.tzinfo is None
                or event.occurred_at.utcoffset() is None):
            raise PlanLinkageDenied("invalid task audit event")
        if index == 0:
            if event.from_status is not None or event.to_status is not TaskStatus.QUEUED:
                raise PlanLinkageDenied("task audit has no valid creation event")
        else:
            if (event.from_status is not previous
                    or event.to_status not in TRANSITIONS[previous]):
                raise PlanLinkageDenied("invalid task audit transition")
        if last_time is not None and event.occurred_at < last_time:
            raise PlanLinkageDenied("task audit time moved backwards")
        previous = event.to_status
        last_time = event.occurred_at
    if previous is not task.status or task.status is not TaskStatus.AWAITING_APPROVAL:
        raise PlanLinkageDenied("task is not awaiting owner approval")


def validate_plan_linkage(task: Task, plan: ProposedPlan, proposal: CodeProposal) -> None:
    """Require the exact queued task and plan that entered the approval hold.

    Task and plan must be supplied by the trusted host, not reconstructed
    from model output or untrusted repository content.
    """
    if type(task) is not Task or type(plan) is not ProposedPlan or type(proposal) is not CodeProposal:
        raise PlanLinkageDenied("trusted task, plan and proposal required")
    _validate_task_history(task)
    if plan.requires_approval is not True:
        raise PlanLinkageDenied("plan must require explicit approval")
    if (plan.task_id != str(task.id) or plan.repository != task.repository
            or plan.title != task.title):
        raise PlanLinkageDenied("plan does not match trusted task")
    if (proposal.request.task_id != task.id
            or proposal.request.repository != task.repository):
        raise PlanLinkageDenied("proposal does not match approved planning scope")


def validate_test_plan_linkage(task: Task, plan: ProposedPlan, request) -> None:
    """Bind a RUN_TESTS request to a trusted pending task and supervised plan.

    This validates scope and lifecycle, not independent proof of owner approval
    or an executable sandbox. The trusted host must supply task and plan.
    """
    from .sandbox import SandboxRequest, SandboxOperation
    if type(task) is not Task or type(plan) is not ProposedPlan or type(request) is not SandboxRequest:
        raise PlanLinkageDenied("trusted task, plan and test request required")
    _validate_task_history(task)
    if plan.requires_approval is not True:
        raise PlanLinkageDenied("plan must require explicit approval")
    if plan.task_id != str(task.id) or plan.repository != task.repository or plan.title != task.title:
        raise PlanLinkageDenied("plan does not match trusted task")
    if request.task_id != task.id or request.repository != task.repository:
        raise PlanLinkageDenied("test request does not match trusted planning scope")
    if request.operation is not SandboxOperation.RUN_TESTS or request.proposal_digest is not None:
        raise PlanLinkageDenied("only unbound test requests can use this authorization path")
