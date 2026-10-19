"""Rules-based Dodger opponent; only the Python standard library is required."""

import argparse
import time
import urllib.error

from client import get_game, send_action


DIRECTIONS = {"Left": -1, "Stay": 0, "Right": 1}


def choose_action(state):
    bot = state["bot"]
    human = state["human"]
    right_edge = state["arena_width"] - 1
    floor = state["arena_height"] - 1

    def position(move, ticks):
        return max(0, min(right_edge, bot["x"] + DIRECTIONS[move] * ticks))

    def score(move):
        cost = 0.0
        for obstacle in state["obstacles"]:
            impact = floor - obstacle["y"]
            if 1 <= impact <= 3:
                x = position(move, impact)
                if obstacle["x"] <= x < obstacle["x"] + obstacle["width"]:
                    cost += 1000
            elif 4 <= impact <= 6:
                x = position(move, 3)
                if obstacle["x"] <= x < obstacle["x"] + obstacle["width"]:
                    cost += 20
        x = position(move, 3)
        cost += abs(x - human["x"]) * 0.05
        cost += (x == 0 or x == right_edge) * 0.2
        if move != "Stay":
            cost += 0.1
        return cost

    move = min(DIRECTIONS, key=score)
    shove = (bot["shove_cooldown_ticks"] == 0 and
             abs(position(move, 1) - human["x"]) <= 1)
    return {"move": move, "shove": shove}


def run(base_url, interval=0.1, max_actions=None):
    sent = 0
    while max_actions is None or sent < max_actions:
        state = get_game(base_url)
        if state["status"] == "Finished":
            return
        try:
            send_action(base_url, 2, choose_action(state))
        except urllib.error.HTTPError as error:
            if error.code == 409:  # The game ended between observation and action.
                return
            raise
        sent += 1
        time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--max-actions", type=int)
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("--interval must be positive")
    try:
        run(args.url, args.interval, args.max_actions)
    except KeyboardInterrupt:
        pass
