# M3.14 — Durable test-request owner approvals (foundation)

The host-only `DurableTestApproval` SQLite ledger stores a single-use,
expiring, revocable owner approval for the **exact bounded** `RUN_TESTS`
request. It binds the task UUID, repository, commit SHA, operation and all
resource limits using a deterministic SHA-256 digest.

The ledger requires a valid local owner session for approval, consumption
and revocation. Consumption uses a transactional conditional update so
concurrent attempts cannot reuse an approval. Invalid request scope,
expired/revoked approvals, altered parameters and replay are rejected.

This is a preparatory capability only. **The execution authorization path
does not yet require or consume this new ledger**; integration and
grant-failure semantics are the next phase. The current `DisabledSandbox`
remains disabled. No filesystem writes, code execution, deployment,
GitHub mutations or production migrations are enabled by this module.

Tests cover persistence across store instances, single-use replay,
concurrency, resource binding, owner-session revocation, expiry,
approval revocation and fail-closed request validation.
