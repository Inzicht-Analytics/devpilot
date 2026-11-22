import io
import json
import unittest
from urllib.error import HTTPError

from devpilot.github_read import (
    GitHubReadAdapter, GitHubReadError, RepositoryNotAllowed, PILOT_REPOSITORY,
)


class FakeResponse:
    def __init__(self, payload):
        self.stream = io.BytesIO(json.dumps(payload).encode())

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        return self.stream.read(size)


class TestGitHubReadAdapter(unittest.TestCase):
    def test_rejects_other_repositories_and_missing_token(self):
        with self.assertRaises(RepositoryNotAllowed):
            GitHubReadAdapter("token", "Inzicht-Analytics/devpilot")
        with self.assertRaises(RepositoryNotAllowed):
            GitHubReadAdapter("token", "bad/path/extra")
        with self.assertRaises(ValueError):
            GitHubReadAdapter("")

    def test_only_get_and_fixed_github_endpoint(self):
        seen = []
        def fake(request, timeout):
            seen.append((request, timeout))
            return FakeResponse([{
                "number": 4, "title": "Test issue", "state": "open",
                "html_url": "https://github.com/Inzicht-Analytics/career-journey/issues/4",
            }, {
                "number": 5, "title": "PR", "state": "open",
                "html_url": "https://github.com/example/pr/5",
                "pull_request": {},
            }])
        adapter = GitHubReadAdapter("secret", transport=fake)
        result = adapter.list_issues()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].number, 4)
        request, timeout = seen[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(timeout, 10)
        self.assertEqual(request.full_url,
            "https://api.github.com/repos/" + PILOT_REPOSITORY +
            "/issues?state=open&per_page=30")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")

    def test_pr_endpoint(self):
        seen = []
        def fake(request, timeout):
            seen.append(request.full_url)
            return FakeResponse([{
                "number": 9, "title": "PR", "state": "open",
                "html_url": "https://github.com/example/pr/9",
            }])
        result = GitHubReadAdapter("secret", transport=fake).list_pull_requests()
        self.assertEqual(result[0].number, 9)
        self.assertTrue(seen[0].endswith("/pulls?state=open&per_page=30"))

    def test_fails_closed_on_api_error_without_token_leak(self):
        def fake(request, timeout):
            raise HTTPError(request.full_url, 403, "denied", {}, None)
        adapter = GitHubReadAdapter("private-token", transport=fake)
        with self.assertRaises(GitHubReadError) as ctx:
            adapter.list_issues()
        self.assertNotIn("private-token", str(ctx.exception))

    def test_rejects_malformed_response(self):
        adapter = GitHubReadAdapter("secret", transport=lambda request, timeout:
                                    FakeResponse({"message": "not a list"}))
        with self.assertRaises(GitHubReadError):
            adapter.list_pull_requests()

    def test_rejects_oversized_response(self):
        class HugeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, size):
                return b"x" * size
        adapter = GitHubReadAdapter("secret", transport=lambda request, timeout:
                                    HugeResponse())
        with self.assertRaises(GitHubReadError):
            adapter.list_issues()
