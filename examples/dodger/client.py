"""Small standard-library client for the Dodger demo's HTTP API."""

import json
import urllib.request


def get_game(base_url):
    with urllib.request.urlopen(f"{base_url}/games/1", timeout=2) as response:
        return json.load(response)


def send_action(base_url, player, action):
    request = urllib.request.Request(
        f"{base_url}/games/1/players/{player}/actions",
        data=json.dumps(action).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=2) as response:
        return json.load(response)
