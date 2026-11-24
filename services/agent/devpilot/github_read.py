"""Read-only GitHub adapter for the Career Journey pilot.

No mutation methods, network calls at import time, or stored credentials.
"""
from dataclasses import dataclass
import json
import base64
import hashlib
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, build_opener, HTTPHandler, HTTPSHandler, HTTPRedirectHandler

from .policy import Action, allowed

PILOT_REPOSITORY = "Inzicht-Analytics/career-journey"
_REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class GitHubReadError(RuntimeError):
    """Read request failed without leaking credentials."""


class RepositoryNotAllowed(ValueError):
    """Repository is not explicitly authorized for the pilot."""


@dataclass(frozen=True)
class GitHubItem:
    number: int
    title: str
    state: str
    url: str


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _transport(request, timeout):
    # Redirects are deliberately disabled to avoid forwarding bearer credentials.
    return build_opener(HTTPHandler(), HTTPSHandler(), _NoRedirect()).open(
        request, timeout=timeout
    )


class GitHubReadAdapter:
    def __init__(self, token: str, repository: str = PILOT_REPOSITORY,
                 transport=None):
        if not isinstance(repository, str) or not _REPO_PATTERN.fullmatch(repository):
            raise RepositoryNotAllowed("invalid repository identifier")
        if repository != PILOT_REPOSITORY:
            raise RepositoryNotAllowed("repository is outside the pilot allowlist")
        if not isinstance(token, str) or not token.strip():
            raise ValueError("a read-only GitHub token is required")
        self._token = token
        self.repository = repository
        self._transport = transport or _transport

    def _get(self, endpoint):
        if not allowed(Action.READ):
            raise GitHubReadError("read policy denied")
        url = "https://api.github.com/repos/" + "/".join(
            quote(part, safe="") for part in self.repository.split("/")
        ) + endpoint
        request = Request(url, method="GET", headers={
            "Authorization": "Bearer " + self._token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "DevPilot-read-only",
        })
        try:
            with self._transport(request, timeout=10) as response:
                raw = response.read(1_000_001)
                if len(raw) > 1_000_000:
                    raise GitHubReadError("response exceeds size limit")
                return json.loads(raw.decode("utf-8"))
        except (HTTPError, URLError, OSError, ValueError, UnicodeError) as exc:
            raise GitHubReadError("GitHub read failed") from None

    @staticmethod
    def _items(data, *, exclude_pull_requests=False):
        if not isinstance(data, list):
            raise GitHubReadError("unexpected GitHub response")
        items = []
        for entry in data:
            if not isinstance(entry, dict):
                raise GitHubReadError("unexpected GitHub item")
            if exclude_pull_requests and "pull_request" in entry:
                continue
            try:
                items.append(GitHubItem(
                    number=int(entry["number"]),
                    title=str(entry["title"]),
                    state=str(entry["state"]),
                    url=str(entry["html_url"]),
                ))
            except (KeyError, TypeError, ValueError):
                raise GitHubReadError("unexpected GitHub item") from None
        return tuple(items)

    def list_issues(self):
        """Return up to 30 open issues, excluding PRs from GitHub's issues API."""
        return self._items(self._get("/issues?state=open&per_page=30"),
                           exclude_pull_requests=True)

    def list_pull_requests(self):
        """Return up to 30 open pull requests."""
        return self._items(self._get("/pulls?state=open&per_page=30"))

    def read_source(self, commit, path):
        """Read a regular file at an immutable commit, never a branch or URL."""
        from .code_generation import _path
        _path(path)
        if type(commit) is not str or not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise GitHubReadError("invalid commit")
        data = self._get("/git/commits/" + commit)
        if not isinstance(data, dict) or data.get("sha") != commit:
            raise GitHubReadError("commit mismatch")
        try:
            tree = data["tree"]["sha"]
            for index, part in enumerate(path.split("/")):
                if not re.fullmatch(r"[0-9a-f]{40}", tree):
                    raise ValueError()
                listing = self._get("/git/trees/" + tree)
                if listing["sha"] != tree or listing.get("truncated") is not False:
                    raise ValueError()
                matches = [entry for entry in listing["tree"] if entry["path"] == part]
                if len(matches) != 1:
                    raise ValueError()
                entry = matches[0]
                last = index == len(path.split("/")) - 1
                if (entry["type"], entry["mode"]) != (("blob", "100644") if last else ("tree", "040000")):
                    raise ValueError()
                tree = entry["sha"]
            if not re.fullmatch(r"[0-9a-f]{40}", tree):
                raise ValueError()
            blob = self._get("/git/blobs/" + tree)
            if blob["sha"] != tree or blob["encoding"] != "base64":
                raise ValueError()
            raw = base64.b64decode(blob["content"].replace("\n", ""), validate=True)
            if len(raw) > 16384 or blob["size"] != len(raw):
                raise ValueError()
            if hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\x00" + raw).hexdigest() != tree:
                raise ValueError()
            return raw.decode("utf-8")
        except (KeyError, TypeError, ValueError, AttributeError):
            raise GitHubReadError("source verification failed") from None
