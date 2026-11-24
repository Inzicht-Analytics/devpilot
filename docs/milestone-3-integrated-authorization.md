# M3.7 Integrated authorization

Proposal-bound public issue calls are denied. The integrated path consumes a durable exact approval before issuing a process-local grant. Failure after consumption burns the approval safely. Approvals expire and can be revoked before consumption; legacy records without expiry fail closed. Revocation after grant issuance requires grant revocation separately. Local SQLite schema upgrade only; no production migration. Trusted host, independent source verification, plan linkage and actual sandbox isolation remain outstanding. No execution enabled.
