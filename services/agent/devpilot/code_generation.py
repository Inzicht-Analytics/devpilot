"""Untrusted model output becomes a proposal, never a filesystem write."""
from dataclasses import dataclass
from typing import Protocol
import re
from uuid import UUID
from .github_read import PILOT_REPOSITORY


class ProposalDenied(ValueError):
    pass


# Deliberately narrow pilot scope; no configuration, auth or infrastructure files.
_ALLOWED = re.compile(r"src/(?:components|pages)/[A-Za-z0-9_-]+\.(?:tsx|css)")


@dataclass(frozen=True)
class SourceFile:
    path: str
    content: str


@dataclass(frozen=True)
class GenerationRequest:
    task_id: UUID
    repository: str
    commit_sha: str
    instruction: str
    sources: tuple[SourceFile, ...]


@dataclass(frozen=True)
class CodeChange:
    path: str
    replacement: str


@dataclass(frozen=True)
class CodeProposal:
    request: GenerationRequest
    changes: tuple[CodeChange, ...]


class Model(Protocol):
    def propose(self, request: GenerationRequest) -> tuple[CodeChange, ...]: ...


def _size(value: str, limit: int) -> int:
    if type(value) is not str or len(value) > limit or "\x00" in value:
        raise ProposalDenied("invalid text")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError:
        raise ProposalDenied("invalid encoding") from None
    if size > limit:
        raise ProposalDenied("text exceeds limit")
    return size


def _path(path: str) -> None:
    if type(path) is not str or len(path) > 160 or not _ALLOWED.fullmatch(path):
        raise ProposalDenied("path outside proposal scope")


def generate(request: GenerationRequest, model: Model) -> CodeProposal:
    if type(request) is not GenerationRequest or type(request.task_id) is not UUID:
        raise ProposalDenied("invalid request")
    if request.repository != PILOT_REPOSITORY:
        raise ProposalDenied("repository outside pilot scope")
    if type(request.commit_sha) is not str or not re.fullmatch(r"[0-9a-f]{40}", request.commit_sha):
        raise ProposalDenied("full commit SHA required")
    if not _size(request.instruction, 4096) or not request.instruction.strip():
        raise ProposalDenied("instruction required")
    if type(request.sources) is not tuple or not 1 <= len(request.sources) <= 5:
        raise ProposalDenied("invalid source count")
    sources = {}
    total = 0
    for source in request.sources:
        if type(source) is not SourceFile:
            raise ProposalDenied("invalid source")
        _path(source.path)
        if source.path in sources:
            raise ProposalDenied("duplicate source")
        total += _size(source.content, 16384)
        sources[source.path] = source.content
    if total > 32768:
        raise ProposalDenied("source budget exceeded")
    changes = model.propose(request)
    if type(changes) is not tuple or not 1 <= len(changes) <= len(sources):
        raise ProposalDenied("invalid change count")
    seen = set()
    total = 0
    for change in changes:
        if type(change) is not CodeChange:
            raise ProposalDenied("invalid change")
        _path(change.path)
        if change.path not in sources or change.path in seen:
            raise ProposalDenied("change outside supplied scope or duplicate")
        total += _size(change.replacement, 16384)
        if not change.replacement.strip() or change.replacement == sources[change.path]:
            raise ProposalDenied("empty or unchanged replacement")
        seen.add(change.path)
    if total > 32768:
        raise ProposalDenied("replacement budget exceeded")
    return CodeProposal(request, changes)
