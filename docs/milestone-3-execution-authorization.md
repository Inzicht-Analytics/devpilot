# Milestone 3.3 — Execution authorization reference ledger

A trusted owner-facing host may explicitly authorize a complete validated
SandboxRequest using an authenticated owner session. Grants bind task UUID,
pilot repository, exact commit SHA, operation and every resource limit.
Grants expire within five minutes and can be revoked or consumed once.
A lock serializes transitions. History records immutable grant snapshots.
Expired grants are recorded when accessed. Restart invalidates all grants.

This is a process-local reference implementation, not durable authorization
or an execution backend. A new grant requires a new explicit owner decision.
The trusted host must display the exact request to the owner before issuance;
never expose owner tokens or ledger mutation methods to the agent. The ledger
does not independently verify task existence, plan approval or commit contents.
Before activation, integrate authoritative task and approval records, durable
atomic grant consumption, timestamped audit storage, verified immutable source
staging and actual sandbox enforcement. Session revocation blocks subsequent
verification but does not cancel in-flight operations.

Existing READ/PLAN policy and DisabledSandbox remain unchanged. No code
execution, repository writes by the agent, deployment or migrations.

## Additional grant-path restriction

The generic `ExecutionAuthorization.issue` path permits `RUN_TESTS` requests only and never accepts a proposal digest. A `VALIDATE_PATCH` grant must instead use the trusted plan-linked, source-verified, durable-approval `issue_proposal` path. This blocks digest-free patch validation from bypassing proposal review. Both paths still use a disabled sandbox and cannot execute processes.
