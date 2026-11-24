# Milestone 3.1 — Sandbox foundation

The sandbox request contract validates pilot repository, task UUID, full commit
SHA, enumerated operation and bounded resource limits. No arbitrary command
strings are accepted. The default backend always denies execution.

IsolationRequirements describes mandatory future backend controls, not an
implemented security boundary: no network, no host mounts or secrets, non-root,
read-only root, disposable workspace, process and workspace quotas. A real
backend must enforce these controls independently of request data, restrict
syscalls and privileges, pin trusted runtime images, safely stage immutable
source, terminate the entire workload on timeout, and bound captured output.
Do not run untrusted code directly on the agent host.

Before activation: integrate real owner authentication, authoritative task and
approval storage, commit- and operation-bound single-use authorization, and
independently test actual isolation and resource enforcement. Treat repository
content and test output as untrusted. No fallback to host execution.

Existing policy remains READ/PLAN only. No GitHub writes, live execution,
deployment, database migration or runtime provisioning is introduced.

Tests: cd services/agent && python -m unittest discover -s tests -v
