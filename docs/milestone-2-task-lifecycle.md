# Milestone 2 Phase 2.1 — Task lifecycle

This is a **pure, in-memory** task state machine. It does not connect to GitHub,
Supabase, an API, a queue, or a worker. No production migration or deployment.

The statuses intentionally match the proposed private Supabase task schema:
`queued`, `planning`, `blocked`, `awaiting_approval`, `completed`,
`failed`, and `cancelled`.

## Allowed transitions

| From | To |
| --- | --- |
| queued | planning, cancelled |
| planning | blocked, awaiting_approval, failed, cancelled |
| blocked | planning, cancelled |
| awaiting_approval | planning, cancelled |
| completed / failed / cancelled | none |

**Completion is intentionally unreachable in this phase.** The approval and
execution subsystems have not been built. `awaiting_approval` is a hold state,
not an authorization to execute. Later phases must bind an authenticated
approval to an exact task/action and re-evaluate permissions before enabling
execution or completion.

`create_task` validates repository and title, then records a UTC creation
event. `transition` returns a new immutable task with an appended event;
invalid transitions, missing reasons, and no-op transitions fail closed.

Audit events are in-memory and **not durable**. Persisted, atomic event storage,
optimistic concurrency, idempotency, actor identity and approval records are
future work, not capabilities claimed by this phase.

## Tests

```sh
cd services/agent
python -m unittest discover -s tests -v
```

Pilot repository: `Inzicht-Analytics/career-journey`. No cross-repository
access is granted by this module.
