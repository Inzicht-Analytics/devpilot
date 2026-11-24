"""Independent read-only source comparison at a pinned commit."""
from .github_read import GitHubReadAdapter, GitHubReadError
from .proposal_validation import dry_run_request


class SourceVerificationDenied(ValueError):
    pass


class SourceVerifier:
    def __init__(self, reader: GitHubReadAdapter):
        if type(reader) is not GitHubReadAdapter:
            raise SourceVerificationDenied("trusted reader required")
        self._reader = reader

    def verify(self, proposal, trusted_commit):
        request = dry_run_request(proposal, trusted_commit)
        if self._reader.repository != request.repository:
            raise SourceVerificationDenied("repository mismatch")
        for source in proposal.request.sources:
            try:
                actual = self._reader.read_source(trusted_commit, source.path)
            except GitHubReadError:
                raise SourceVerificationDenied("source unavailable") from None
            if actual != source.content:
                raise SourceVerificationDenied("source content mismatch")
        return request
