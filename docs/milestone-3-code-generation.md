# Milestone 3.4 — Controlled code generation

A trusted host supplies a bounded request with task UUID, pilot repository,
full commit SHA, instruction and existing source text. A pluggable Model
protocol returns proposed full-file replacements. No live model is configured.
Only existing supplied files directly under src/components or src/pages
with tsx/css extensions are permitted. No creation, deletion, configuration,
workflow or infrastructure changes. Up to five files, 16 KiB each and 32 KiB
aggregate per input/output. Duplicate paths and invalid text are rejected.

These are lexical scope checks, not a guarantee of safe code. Source text
and model output are untrusted. Before connecting a real model, verify source
provenance at the pinned commit, obtain explicit permission to transmit source,
screen for secrets, and enforce provider timeout and response limits. A trusted
adapter must not have write tools or credentials for repository mutation.
Before applying any proposal, verify actual tree paths and file modes, reject
symlinks and case collisions, validate content and bind approval to the exact
proposal digest. No source is fetched, transmitted, written or executed here.
Existing policy remains READ/PLAN only. No deployment or migration.
