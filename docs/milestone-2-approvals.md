# Milestone 2 Phase 2.4 — Controlled approval records

This phase adds a pure in-memory `decide` function for owner decisions on proposals in `awaiting_approval`.

- An explicit reviewer identifier, decision enum and nonempty reason are mandatory. **The caller must authenticate the reviewer**; a supplied identifier is not authentication.
- Each immutable approval record contains a SHA-256 digest of the exact proposal content, task and repository identity, decision, reason, and UTC timestamp.
- Rejecting a proposal transitions the task to `cancelled` with an audit event.
- Approving a proposal **does not change the task state**: it stays `awaiting_approval`. The record is evidence of a decision, **not permission to execute**. No task completion or mutating GitHub action is enabled.
- Only the Career Journey pilot repository is accepted. Stale task IDs, changed titles, invalid statuses and missing reasons fail closed.
- Decisions are not persisted, and there is no authentication, API, worker, token provisioning, deployment, or migration in this phase.

Next phases must implement authenticated owner identity, durable records, one-time consumption and commit-bound authorization before any write capability is considered.

Tests: `cd services/agent && python -m unittest discover -s tests -v`.
