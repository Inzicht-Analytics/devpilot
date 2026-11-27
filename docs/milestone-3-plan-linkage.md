# M3.10 — Supervised plan linkage (offline validation)

This phase introduces `validate_plan_linkage`, an explicit, fail-closed
check that a code proposal refers to the same trusted task and reviewable
plan that entered the `awaiting_approval` lifecycle state.

It checks:
- Exact task UUID and repository match the proposal request.
- The task remains `awaiting_approval`, with a consistent latest audit event.
- The trusted plan references the same task ID, repository, and title.
- The plan retains `requires_approval=True`; no implied consent.

Inputs must be supplied from trusted orchestration and planning storage;
a model-provided plan or task snapshot is not proof of owner approval.

**Scope limitation:** This is an offline preparatory guard, not yet wired
into `ExecutionAuthorization.issue_proposal`. A later integration must
require host-bound task and plan evidence at the authorization boundary,
with approval/store and replay tests. No sandbox execution, repository
write, deployment, or database migration is enabled.
