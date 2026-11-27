# M3.15 — Enforce durable owner approvals for test grants

The `ExecutionAuthorization.issue` path now requires an existing
`DurableTestApproval` instance tied to the same owner authentication
context, and an approval ID for the **exact** bounded `RUN_TESTS`
request. Missing stores, missing approvals, revoked or expired approvals,
modified request fields and replay fail closed.

The order of checks is important:
1. Validate the bounded request and restrict the generic path to `RUN_TESTS`.
2. Verify the trusted task/plan identity and `AWAITING_APPROVAL` state.
3. Validate the requested grant lifetime and authenticated owner session.
4. Atomically consume the durable, single-use exact-request approval.
5. Issue a short-lived process-local grant.

Failures before durable consumption do not burn an approval; a later failure
after consumption may burn it safely without issuing a grant. Grant usage
still requires exact-request matching and one-time consumption.

This supersedes the foundation-only stage: the durable test approval is now
mandatory at grant issuance, but it remains a reference implementation.
Trusted host provenance for task and plan objects, independent verification
of test sources, and runtime isolation require further review before
activation. `DisabledSandbox` remains disabled. No repository write,
deployment or production database migration is enabled.
