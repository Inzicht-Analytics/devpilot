import unittest
from devpilot.runtime import run, MockAdapter

class RuntimeTests(unittest.TestCase):
    def test_mock_stops_at_approval(self):
        result = run(MockAdapter())
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["status"], "awaiting_approval")
        self.assertIs(result[0]["requires_approval"], True)

    def test_budget(self):
        for count in (0, 6, True, 1.5):
            with self.assertRaises(ValueError):
                run(MockAdapter(), count)

    def test_snapshot_reused(self):
        class CountingAdapter(MockAdapter):
            calls = 0
            def list_issues(self):
                self.calls += 1
                return super().list_issues()
        adapter = CountingAdapter()
        results = run(adapter, 5)
        self.assertEqual(adapter.calls, 1)
        self.assertEqual(len({r["task_id"] for r in results}), 5)

    def test_wrong_repository(self):
        adapter = MockAdapter()
        adapter.repository = "other/repo"
        with self.assertRaises(ValueError):
            run(adapter)
