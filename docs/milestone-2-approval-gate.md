# Milestone 2.5 — Owner verification boundary and replay protection

ApprovalGate is an in-memory service boundary, not an authentication provider.
Trusted application code configures an owner subject and a credential verifier
that must validate credentials and return a stable authenticated subject.
No production verifier or endpoint is provided. Test credentials are fixtures only.

Trusted code registers a pending task and the digest of its proposal. Submission
requires the verified owner, registered task and matching proposal digest.
A lock serializes decisions; each registered task can receive only one decision
within this gate instance. Failed validation does not consume the decision.
History returns immutable records. Credentials are not stored in records.

Approval remains a hold, rejection cancels. No execution authority is granted.
The original pure decide function is an internal record builder, not a public
authorization endpoint. Future integrations must use the gate rather than
expose that builder directly.

Replay protection is process-local, not durable or distributed. Restarting or
creating another gate loses the guarantee. Before production integration,
implement real authentication, durable atomic storage, expiry/revocation,
commit binding, and authorization checks at the execution boundary.
No database migration, deployment or GitHub mutation capability is added.

Tests: cd services/agent && python -m unittest discover -s tests -v
