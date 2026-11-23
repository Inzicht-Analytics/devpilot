# Milestone 2 Phase 2.3 — Supervised task planning

This phase connects the in-memory lifecycle to the read-only GitHub adapter
through a **caller-invoked** planning function. The adapter reads the first
page (at most 30) of open issues and pull requests in the allowlisted
`Inzicht-Analytics/career-journey` repository.

`gather_snapshot(adapter)` checks the repository allowlist and read policy,
then gathers immutable metadata. `prepare_plan(task, snapshot)` requires a
queued task in the same repository, checks planning policy, and transitions
`queued -> planning -> awaiting_approval` with audit events.

The proposal contains **counts only** rather than untrusted issue titles or
pull request descriptions, so repository content is not promoted to agent
instructions. Proposed steps are fixed review/acceptance/approval guidance,
not executable commands.

**No approval is granted by this module.** The awaiting-approval state
remains a hold; no transitions to completed, code writes, branch creation,
PR creation, merge, deployment or database operations are enabled.

No live worker, task persistence, token provisioning, API endpoint or
automatic scheduling is added. Callers must provide a configured read-only
adapter and handle read errors; failures do not change the original task.

Run tests with:

```sh
cd services/agent
python -m unittest discover -s tests -v
```
