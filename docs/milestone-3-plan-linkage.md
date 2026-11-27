# M3.11 — Enforced supervised plan linkage at authorization

The proposal authorization boundary now calls `validate_plan_linkage`
with trusted-host task and plan values **before** independent pinned-source
verification and before consuming a durable single-use approval.

Missing, stale, mismatched or non-awaiting-approval planning context denies
grant issuance and leaves the durable approval unconsumed.

This extends the offline validation introduced in M3.10; callers of
`authorize_dry_run` must supply `task` and `plan` from the trusted
orchestrator, not from model output. Validation of identity and workflow
state does **not** demonstrate that an owner has approved the plan; the
existing durable owner-approval check remains mandatory.

## Tests
- Matching task, plan and proposal can proceed through existing source
  verification and single-use approval checks.
- Missing or forged plan, or a task returned to planning, fails closed
  without spending an approval.
- Source verification, one-use grants and DisabledSandbox remain intact.

No live sandbox, GitHub write path, database migration or deployment is enabled.
