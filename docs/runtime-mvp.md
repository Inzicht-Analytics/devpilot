# Read-only runtime candidate

Run from services/agent: python -m devpilot.runtime

The default uses synthetic metadata and the existing deterministic planner (a mock reasoning path, not a live model). It creates an in-memory task and stops at awaiting approval. The manual workflow uses no credentials beyond its read-only checkout token, has no schedule, and cannot execute proposed changes.

Optional local live metadata read: python -m devpilot.runtime --live-read. Requires an independently provisioned least-privilege DEVPILOT_READ_TOKEN for Career Journey; no credential is provisioned by this change. Only counts are emitted, not issue titles. Snapshot is limited to first-page metadata and reused across at most five synthetic tasks per invocation. This is not a durable queue; repeated invocations create new task IDs. No autonomous writes, sandbox execution, persistent memory or live AI integration are enabled.

Next: authoritative task registry, durable deduplication, provider abstraction and failure recovery. Verify exact-head CI before merge; manual workflow activation requires separate approval.
