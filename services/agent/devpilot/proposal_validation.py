"""Offline proposal validation; never applies or executes changes."""
from dataclasses import asdict
from hashlib import sha256
import json

from .code_generation import CodeProposal, ProposalDenied, generate
from .sandbox import SandboxRequest, SandboxOperation, validate_request


class _Replay:
    def __init__(self, changes):
        self.changes = changes

    def propose(self, request):
        return self.changes


def dry_run_request(proposal: CodeProposal, trusted_commit: str) -> SandboxRequest:
    """Trusted host supplies the current verified source commit, not the model."""
    if type(proposal) is not CodeProposal:
        raise ProposalDenied("invalid proposal")
    checked = generate(proposal.request, _Replay(proposal.changes))
    request = checked.request
    if type(trusted_commit) is not str or request.commit_sha != trusted_commit:
        raise ProposalDenied("stale source commit")
    payload = asdict(checked)
    payload["request"]["task_id"] = str(request.task_id)
    digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True).encode("ascii")).hexdigest()
    result = SandboxRequest(request.task_id, request.repository, request.commit_sha,
                            SandboxOperation.VALIDATE_PATCH, proposal_digest=digest)
    validate_request(result)
    return result


def authorize_dry_run(ledger, proposal, trusted_commit, token, ttl_seconds=60, *, approval_id=None):
    """Explicit owner authorization; separate from plan approval."""
    return ledger.issue_proposal(approval_id, proposal, trusted_commit, token, ttl_seconds)


def consume_dry_run(ledger, grant_id, proposal, trusted_commit, token):
    """Consume exact authorization only; no sandbox execution or file writes."""
    return ledger.consume(grant_id, dry_run_request(proposal, trusted_commit), token)
