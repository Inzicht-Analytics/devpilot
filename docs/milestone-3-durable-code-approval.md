# M3.6 durable code proposal approval

Local SQLite reference ledger binds an explicit authenticated owner decision to task, repository, source commit and complete proposal digest. One approval per task; transactional conditional update prevents replay across connections. Consumption returns only a validated offline sandbox request, never executes or issues a grant. Existing execution authorization remains separate and disabled sandbox remains mandatory.

Trusted host must verify source contents and commit independently. Persistent plan-to-code linkage, approval expiry/revocation, and mandatory integration with execution authorization remain future work. No production database migration or deployment. Local database must be protected from agent access. CI and explicit merge approval required.
