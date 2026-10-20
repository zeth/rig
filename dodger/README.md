# Dodger

You're a little box at the bottom, obstacles fall from the top, move left/right and survive as long as possible.

```text
        ■

              ■

    ■

          ▲
────────────────
```

That's probably the absolute minimum viable **arcade game**: player movement + falling objects + collision + score. You could teach the whole idea of a game in perhaps 100–200 lines without obscuring it behind game-specific rules.

Things fall. Don't get hit.

Something instead of the same boring examples.

`api.hpp` is the C++20 API declaration used by RIG's reflection prototype.
`openapi.json` is generated from it. `game.cpp` implements a small deterministic
simulation, and `server.cpp` serves the declared routes on localhost.
`inspect.cpp` nominates the `dodger` namespace; RIG discovers the annotated
operations and their reachable types without a separate declaration list.
The routes declare a shared `ErrorResponse` type and their 400, 404, and 409
responses with `RIG_ERROR`; these appear in the generated OpenAPI document.

The sample contract now has left/stay/right actions, player lives and shove
cooldowns, falling obstacles, and a waiting/running/finished game status. A
winner is `null` until the game ends. Both players start with three lives and
the same movement speed and shove cooldown. Obstacles appear every five ticks;
the game runs at about 30 ticks per second after each player submits an action.
The most recent action remains in effect until that player sends another.

From the repository root, run `make server`, then use either player endpoint:

```sh
curl http://127.0.0.1:8765/games/1
curl -X POST http://127.0.0.1:8765/games/1/players/1/actions \
  -H 'Content-Type: application/json' -d '{"move":"Right","shove":false}'
curl -X POST http://127.0.0.1:8765/games/1/players/2/actions \
  -H 'Content-Type: application/json' -d '{"move":"Left","shove":false}'
```

For a playable match, run `make play` in a terminal. It starts the server, a
Python bot using the HTTP API, and a terminal client for the human player.
Use A/D or the arrow keys to move, Space to shove, and Q to quit. Hold a
movement key to keep moving; the most recent key is applied for one client
update (about three simulation ticks). Restart `make play` for a new game.

The bot uses only Python's standard library. Every tenth of a second, it
reads the game state, compares left/stay/right against the next few obstacle
positions, and sends its action over HTTP. It sees the same state and has the
same movement and shove rules as the human client. `python3 dodger/bot.py`
can also connect to a separately running `make server` instance.

The demo hosts one game (`id` 1). The HTTP listener is intentionally limited
to localhost and basic JSON requests.
