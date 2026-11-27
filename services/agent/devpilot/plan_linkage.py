"""Offline trusted-host linkage of a code proposal to a supervised plan.

This gate validates identities only. It does not approve a plan, consume
an approval, issue a grant, run a sandbox or write to a repository.
"""
from .orchestrator import Task, TaskStatus
from .planning import ProposedPlan
from .code_generation import CodeProposal


class PlanLinkageDenied(ValueError):
    """Proposal does not match the trusted task and reviewed plan."""


def validate_plan_linkage(task: Task, plan: ProposedPlan, proposal: CodeProposal) -> None:
    """Require the exact queued task and plan that entered the approval hold.

    Task and plan must be supplied by the trusted host, not reconstructed
    from model output or untrusted repository content.
    """
    if type(task) is not Task or type(plan) is not ProposedPlan or type(proposal) is not CodeProposal:
        raise PlanLinkageDenied("trusted task, plan and proposal required")
    if task.status is not TaskStatus.AWAITING_APPROVAL:
        raise PlanLinkageDenied("task is not awaiting owner approval")
    if not task.events or task.events[-1].to_status is not TaskStatus.AWAITING_APPROVAL:
        raise PlanLinkageDenied("task audit state is inconsistent")
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
    if task.status is not TaskStatus.AWAITING_APPROVAL:
        raise PlanLinkageDenied("task is not awaiting owner approval")
    if not task.events or task.events[-1].to_status is not TaskStatus.AWAITING_APPROVAL:
        raise PlanLinkageDenied("task audit state is inconsistent")
    if plan.requires_approval is not True:
        raise PlanLinkageDenied("plan must require explicit approval")
    if plan.task_id != str(task.id) or plan.repository != task.repository or plan.title != task.title:
        raise PlanLinkageDenied("plan does not match trusted task")
    if request.task_id != task.id or request.repository != task.repository:
        raise PlanLinkageDenied("test request does not match trusted planning scope")
    if request.operation is not SandboxOperation.RUN_TESTS or request.proposal_digest is not None:
        raise PlanLinkageDenied("only unbound test requests can use this authorization path")
