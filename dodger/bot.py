"""Rules-based Dodger opponent using the client generated from OpenAPI."""

import argparse
import sys
import time
from http import HTTPStatus
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "build"))

from dodger_api_client import Client
from dodger_api_client.api.default import get_game, submit_action
from dodger_api_client.models import Action, GameState, GameStatus, Move


DIRECTIONS = {Move.LEFT: -1, Move.STAY: 0, Move.RIGHT: 1}


def choose_action(state):
    bot = state.bot
    human = state.human
    right_edge = state.arena_width - 1
    floor = state.arena_height - 1

    def position(move, ticks):
        return max(0, min(right_edge, bot.x + DIRECTIONS[move] * ticks))

    def score(move):
        cost = 0.0
        for obstacle in state.obstacles:
            impact = floor - obstacle.y
            if 1 <= impact <= 3:
                x = position(move, impact)
                if obstacle.x <= x < obstacle.x + obstacle.width:
                    cost += 1000
            elif 4 <= impact <= 6:
                x = position(move, 3)
                if obstacle.x <= x < obstacle.x + obstacle.width:
                    cost += 20
        x = position(move, 3)
        cost += abs(x - human.x) * 0.05
        cost += (x == 0 or x == right_edge) * 0.2
        if move != Move.STAY:
            cost += 0.1
        return cost

    move = min(DIRECTIONS, key=score)
    shove = (bot.shove_cooldown_ticks == 0 and
             abs(position(move, 1) - human.x) <= 1)
    return Action(move=move, shove=shove)


def run(base_url, interval=0.1, max_actions=None):
    sent = 0
    with Client(base_url=base_url, timeout=httpx.Timeout(2.0),
                raise_on_unexpected_status=True) as client:
        while max_actions is None or sent < max_actions:
            observed = get_game.sync_detailed(id=1, client=client)
            if observed.status_code != HTTPStatus.OK or not isinstance(observed.parsed, GameState):
                raise RuntimeError(f"could not read game: {observed.parsed}")
            state = observed.parsed
            if state.status == GameStatus.FINISHED:
                return
            submitted = submit_action.sync_detailed(
                id=1, client=client, body=choose_action(state)
            )
            if submitted.status_code == HTTPStatus.CONFLICT:
                return  # The game ended between observation and action.
            if submitted.status_code != HTTPStatus.OK or not isinstance(submitted.parsed, GameState):
                raise RuntimeError(f"could not submit action: {submitted.parsed}")
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
