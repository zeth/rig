import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dodger"))

from bot import choose_action
from terminal import render


class BotTests(unittest.TestCase):
    def setUp(self):
        self.state = {
            "arena_width": 20,
            "arena_height": 12,
            "tick": 10,
            "status": "Running",
            "winner": None,
            "human": {"x": 3, "lives": 3, "shove_cooldown_ticks": 0},
            "bot": {"x": 5, "lives": 3, "shove_cooldown_ticks": 0},
            "obstacles": [],
        }

    def test_bot_dodges_imminent_obstacle(self):
        self.state["obstacles"] = [{"x": 5, "y": 10, "width": 2}]
        self.assertEqual(choose_action(self.state)["move"], "Left")

    def test_bot_shoves_when_in_range(self):
        self.state["human"]["x"] = 5
        self.assertTrue(choose_action(self.state)["shove"])
        self.state["bot"]["shove_cooldown_ticks"] = 2
        self.assertFalse(choose_action(self.state)["shove"])

    def test_terminal_renders_state(self):
        self.state["obstacles"] = [{"x": 1, "y": 2, "width": 2}]
        lines = render(self.state)
        self.assertIn("##", lines[3])
        self.assertIn("H", lines[12])
        self.assertIn("B", lines[12])


if __name__ == "__main__":
    unittest.main()
