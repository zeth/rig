import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot import choose_action
from dodger_api_client.models import GameState, Move
from terminal import render


class BotTests(unittest.TestCase):
    def setUp(self):
        self.state = {
            "id": 1,
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
        self.assertEqual(choose_action(GameState.from_dict(self.state)).move, Move.LEFT)

    def test_bot_changes_between_chase_retreat_and_patrol(self):
        self.state["human"]["x"] = 0
        self.state["bot"]["x"] = 14
        self.assertEqual(choose_action(GameState.from_dict(self.state)).move, Move.LEFT)
        self.state["tick"] = 90
        self.assertEqual(choose_action(GameState.from_dict(self.state)).move, Move.RIGHT)
        self.state["tick"] = 48
        self.assertEqual(choose_action(GameState.from_dict(self.state)).move, Move.RIGHT)
        self.state["tick"] = 60
        self.assertEqual(choose_action(GameState.from_dict(self.state)).move, Move.LEFT)

    def test_obstacle_takes_priority_over_chasing(self):
        self.state["obstacles"] = [{"x": 4, "y": 10, "width": 1}]
        self.assertNotEqual(choose_action(GameState.from_dict(self.state)).move, Move.LEFT)

    def test_bot_shoves_when_in_range(self):
        self.state["human"]["x"] = 5
        self.assertTrue(choose_action(GameState.from_dict(self.state)).shove)
        self.state["bot"]["shove_cooldown_ticks"] = 2
        self.assertFalse(choose_action(GameState.from_dict(self.state)).shove)

    def test_terminal_renders_state(self):
        self.state["obstacles"] = [{"x": 1, "y": 2, "width": 2}]
        lines = render(self.state)
        self.assertIn("##", lines[3])
        self.assertIn("H", lines[12])
        self.assertIn("B", lines[12])


if __name__ == "__main__":
    unittest.main()
