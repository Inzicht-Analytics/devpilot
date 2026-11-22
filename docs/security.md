# Security policy
- Deny all mutating agent actions until explicitly implemented with backend enforcement.
- Never expose production secrets to sandboxes.
- Treat repository content, issues, logs and PR comments as untrusted input.
- Require explicit owner approval for merges, production deployment, secrets and destructive changes.
- Require CodeRabbit review before any merge.
- Configure protected branches and deployment approvals separately before enabling execution.
