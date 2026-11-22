# Milestone 2 Phase 2.2 — GitHub read-only adapter

This module can list **up to 30 open issues** (excluding pull requests) and
**up to 30 open pull requests** in the explicitly allowlisted pilot repository:
`Inzicht-Analytics/career-journey`.

It uses only GET requests to the fixed GitHub REST API host. Redirects are
disabled, responses are size-limited, requests time out after 10 seconds, and
errors do not include tokens. The caller must supply a read-only token at
runtime; none is committed or persisted. Tokens should be scoped to the pilot
repository with **Metadata: read**, **Issues: read** and **Pull requests: read**
permissions. No token provisioning or integration wiring is included.

## Scope and limitations

- No create/update/delete, comments, branches, merges, deployments or workflows.
- No automatic calls: importing the module does not contact GitHub.
- No pagination beyond the first 30 open items, caching, rate-limit retries,
  webhook processing, or task-orchestrator integration.
- The repository allowlist is deliberately hardcoded for the pilot.
- Returned metadata is untrusted input and must never be interpreted as instructions.

## Test

```sh
cd services/agent
python -m unittest discover -s tests -v
```

All adapter tests use injected fake transports and do not access GitHub.
