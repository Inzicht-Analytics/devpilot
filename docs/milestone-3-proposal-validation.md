# M3.5 proposal validation (offline reference)

Revalidate all generated proposal fields with the existing generation constraints without calling a model. Hash the complete validated proposal, including source contents, task, repository, instruction, commit and replacements. Bind the digest to the sandbox request so the existing single-use owner authorization ledger compares it on consumption.

The trusted host must independently obtain the current source commit and source contents; this module does not fetch or authenticate repository snapshots. The dry-run functions only construct and consume authorization records. They do not execute tests, apply patches, write files or grant real execution. Existing plan approvals remain separate; durable linkage of plan approval, code proposal and execution grants is still outstanding. The default sandbox remains disabled. No migrations or deployments.

Before merge: run Foundation CI and review the exact head. CodeRabbit temporarily optional per owner instruction. Separate explicit merge approval required.
