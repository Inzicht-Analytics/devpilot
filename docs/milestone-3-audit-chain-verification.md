# M3.16 — Validate complete supervised task audit chains

Authorization now rejects a task snapshot whose apparent final
`AWAITING_APPROVAL` status conceals an inconsistent lifecycle history.
Both code-proposal and generic test-grant plan-linkage validators inspect
the **full** task event sequence.

The audit validator requires an initial `QUEUED` creation event, the same
task UUID on every event, permitted consecutive status transitions, complete
and nonempty reasons, timezone-aware timestamps without backwards jumps,
and consistency between the final event and the current pending status.
A valid replanning history is accepted.

This is internal integrity checking, **not** proof that task/plan objects
came from a trusted host or persistent authoritative store. A separately
authenticated, durable host-side task/plan registry remains necessary before
activating the sandbox. It does not enable a test runner, a GitHub mutation,
a deployment, or any production database migration.
