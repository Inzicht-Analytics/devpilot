# Milestone 2.6 — Persistent approval storage

The SQLite reference adapter stores registered task identity, repository, title,
proposal digest, and one decision per task. BEGIN IMMEDIATE serializes decision
transactions across connections to the same local database. A primary key
prevents re-registration. History is retrievable after reopening the database.

The schema is supplied as an unapplied migration. Only tests initialize temporary
databases. No live database is configured or modified. This is not a Supabase
migration or a distributed production storage implementation.

Trusted application code must supply the original task and proposal, register
them, and provide a real credential verifier. Full task event persistence and
reconstruction are not included; the resulting status and decision metadata
are persisted. Credentials are not stored. Protect the database file and use
the same database across restarts. Approval still grants no execution rights.

Before production: integrate authenticated identity, authoritative task storage,
database access controls, expiry/revocation and commit-bound execution checks.
Run tests: cd services/agent && python -m unittest discover -s tests -v
