"""Deterministic, network-free verification of pinned GitHub object traversal."""
import base64
import hashlib
import io
import json
import unittest

from devpilot.github_read import GitHubReadAdapter, GitHubReadError


def oid(kind, raw):
    return hashlib.sha1(kind.encode() + b" " + str(len(raw)).encode() + b"\\x00" + raw).hexdigest()


class Response:
    def __init__(self, data):
        self.data = io.BytesIO(json.dumps(data).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, size):
        return self.data.read(size)


class TestPinnedSourceTraversal(unittest.TestCase):
    def setUp(self):
        self.path = "src/pages/Home.tsx"
        self.data = b"export const title = 'ok';\\n"
        self.blob = oid("blob", self.data)
        self.page_tree = "1" * 40
        self.src_tree = "2" * 40
        self.root_tree = "3" * 40
        self.commit = "4" * 40
        self.routes = {
            "/git/commits/" + self.commit: {
                "sha": self.commit, "tree": {"sha": self.root_tree},
            },
            "/git/trees/" + self.root_tree: {
                "sha": self.root_tree, "truncated": False,
                "tree": [{"path": "src", "type": "tree", "mode": "040000", "sha": self.src_tree}],
            },
            "/git/trees/" + self.src_tree: {
                "sha": self.src_tree, "truncated": False,
                "tree": [{"path": "pages", "type": "tree", "mode": "040000", "sha": self.page_tree}],
            },
            "/git/trees/" + self.page_tree: {
                "sha": self.page_tree, "truncated": False,
                "tree": [{"path": "Home.tsx", "type": "blob", "mode": "100644", "sha": self.blob}],
            },
            "/git/blobs/" + self.blob: {
                "sha": self.blob, "size": len(self.data), "encoding": "base64",
                "content": base64.b64encode(self.data).decode(),
            },
        }
        self.seen = []

    def reader(self):
        def transport(request, timeout):
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(timeout, 10)
            self.seen.append(request.full_url)
            prefix = "https://api.github.com/repos/Inzicht-Analytics/career-journey"
            if not request.full_url.startswith(prefix):
                raise AssertionError("request escaped expected GitHub repository")
            return Response(self.routes[request.full_url[len(prefix):]])
        return GitHubReadAdapter("fixture", transport=transport)

    def test_traverses_exact_tree_and_verifies_blob_hash(self):
        self.assertEqual(self.reader().read_source(self.commit, self.path), self.data.decode())
        self.assertEqual(len(self.seen), 5)

    def test_rejects_changed_commit_response(self):
        self.routes["/git/commits/" + self.commit]["sha"] = "5" * 40
        with self.assertRaises(GitHubReadError):
            self.reader().read_source(self.commit, self.path)

    def test_rejects_truncated_tree(self):
        self.routes["/git/trees/" + self.root_tree]["truncated"] = True
        with self.assertRaises(GitHubReadError):
            self.reader().read_source(self.commit, self.path)

    def test_rejects_duplicate_tree_entries(self):
        page = self.routes["/git/trees/" + self.page_tree]["tree"]
        page.append(dict(page[0]))
        with self.assertRaises(GitHubReadError):
            self.reader().read_source(self.commit, self.path)

    def test_rejects_symlink_and_executable_modes(self):
        page = self.routes["/git/trees/" + self.page_tree]["tree"][0]
        for mode in ("120000", "100755"):
            with self.subTest(mode=mode):
                page["mode"] = mode
                with self.assertRaises(GitHubReadError):
                    self.reader().read_source(self.commit, self.path)

    def test_rejects_missing_or_wrong_tree(self):
        self.routes["/git/trees/" + self.src_tree]["sha"] = "6" * 40
        with self.assertRaises(GitHubReadError):
            self.reader().read_source(self.commit, self.path)

    def test_rejects_tampered_blob_content(self):
        self.routes["/git/blobs/" + self.blob]["content"] = base64.b64encode(
            b"export const title = 'no';\\n").decode()
        with self.assertRaises(GitHubReadError):
            self.reader().read_source(self.commit, self.path)

    def test_rejects_invalid_utf8_and_oversized_source(self):
        for payload in (b"\\xff", b"a" * 16385):
            with self.subTest(length=len(payload)):
                new_hash = oid("blob", payload)
                page = self.routes["/git/trees/" + self.page_tree]["tree"][0]
                page["sha"] = new_hash
                self.routes["/git/blobs/" + new_hash] = {
                    "sha": new_hash, "size": len(payload), "encoding": "base64",
                    "content": base64.b64encode(payload).decode(),
                }
                with self.assertRaises(GitHubReadError):
                    self.reader().read_source(self.commit, self.path)

    def test_rejects_branch_name_as_commit(self):
        with self.assertRaises(GitHubReadError):
            self.reader().read_source("main", self.path)
        self.assertEqual(self.seen, [])
