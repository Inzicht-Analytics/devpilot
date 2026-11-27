# M3.9: Enforce pinned-source verification at proposal authorization

The trusted-host execution authorization path now requires a concrete
`SourceVerifier` to issue an authorization for an approved code proposal.
A missing verifier fails closed. The verifier compares the exact proposal
sources against pinned GitHub commit/tree/blob data through the read-only
adapter before consuming the durable single-use approval.

If source verification fails, no authorization grant is issued and the
durable approval is not consumed. The owner can correct stale source data
and retry. A successful verification still requires the existing owner
session, durable approval, exact request binding and short-lived grant.

## Constraints
- This does **not** enable real code execution: `DisabledSandbox` remains
  disabled and there is no repository-write path.
- Trust still rests on host-provided GitHub credentials, commit SHA and
  adapter; repository content is never an authorization instruction.
- This is a proposal-authorization boundary, not a promise that later source
  reads cannot change or that runtime sandbox isolation is complete.
- Deployment and merges require separate explicit owner approval.

## Regression tests
- Correct pinned source can be verified before issuance.
- A forged source fails closed without burning the durable approval.
- Missing source verifier fails closed without consuming an approval.
- Existing one-time grant and approval replay protections remain intact.
