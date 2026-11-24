# Milestone 3.2 — Local owner authentication

OwnerAuth verifies possession of a securely provisioned random 32-byte owner
key and issues opaque random session tokens. Only token hashes are retained;
sessions expire using monotonic time, support revocation and are limited to 16.
Restart invalidates all sessions. No real credentials are committed.

Trusted host code can pass auth.verify to ApprovalGate or
PersistentApprovalGate with the same configured owner subject. The agent and
sandbox must never receive the owner key or session tokens. The owner subject
is configured locally; this is not external identity verification or MFA.

No HTTP endpoint, browser login, credential provisioning, production identity
provider or deployment is included. Before exposing a service, implement
secure transport, rate limiting, protected secret provisioning, owner
enrollment and recovery, session handling and audit controls. Revocation
prevents subsequent verification; it does not cancel an already verified
in-flight decision. Approval still grants no execution rights.

Tests: cd services/agent && python -m unittest discover -s tests -v
