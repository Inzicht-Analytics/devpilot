"""Sandbox contract only. No process, container, filesystem or network execution."""
from dataclasses import dataclass
from enum import Enum
import re
from uuid import UUID

from .github_read import PILOT_REPOSITORY


class SandboxDenied(ValueError):
    """Sandbox request is invalid or execution is unavailable."""


class SandboxOperation(str, Enum):
    VALIDATE_PATCH = "validate_patch"
    RUN_TESTS = "run_tests"


@dataclass(frozen=True)
class SandboxRequest:
    task_id: UUID
    repository: str
    commit_sha: str
    operation: SandboxOperation
    timeout_seconds: int = 60
    memory_mib: int = 256
    cpu_count: int = 1
    output_bytes: int = 65536


@dataclass(frozen=True)
class IsolationRequirements:
    network_disabled: bool = True
    non_root: bool = True
    read_only_root: bool = True
    ephemeral_workspace: bool = True
    host_mounts_disabled: bool = True
    secrets_disabled: bool = True
    process_limit: int = 64
    workspace_bytes: int = 64 * 1024 * 1024


def validate_request(request: SandboxRequest) -> IsolationRequirements:
    """Validate a bounded request; this does not establish actual isolation."""
    if not isinstance(request, SandboxRequest) or not isinstance(request.task_id, UUID):
        raise SandboxDenied("invalid task")
    if request.repository != PILOT_REPOSITORY:
        raise SandboxDenied("repository outside pilot allowlist")
    if not isinstance(request.commit_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", request.commit_sha):
        raise SandboxDenied("full commit SHA required")
    if not isinstance(request.operation, SandboxOperation):
        raise SandboxDenied("operation outside allowlist")
    for value, maximum in ((request.timeout_seconds, 120), (request.memory_mib, 512),
                           (request.cpu_count, 2), (request.output_bytes, 65536)):
        if type(value) is not int or not 1 <= value <= maximum:
            raise SandboxDenied("resource limit outside allowed range")
    return IsolationRequirements()


class DisabledSandbox:
    """Default backend cannot execute anything, even a valid request."""

    def execute(self, request: SandboxRequest):
        validate_request(request)
        raise SandboxDenied("execution disabled: isolated backend and authorization required")
