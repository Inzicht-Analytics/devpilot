import unittest
from devpilot.policy import Action, allowed
class TestPolicy(unittest.TestCase):
    def test_read_and_plan(self):
        self.assertTrue(allowed(Action.READ))
        self.assertTrue(allowed(Action.PLAN))
    def test_mutations_blocked(self):
        for action in Action:
            if action not in (Action.READ, Action.PLAN):
                with self.subTest(action=action):
                    self.assertFalse(allowed(action))
