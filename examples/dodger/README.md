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
The server compiles a C++20 JSON codec generated from the same reflected API
data as `openapi.json`. It also uses generated route dispatch; socket and HTTP
framing code remain local.
The Makefile passes `api.hpp` and the `dodger` namespace to the installed
`rig inspect` command. RIG discovers the annotated operations and their
reachable types without a separate declaration list or C++26 app code.
The routes declare a shared `ErrorResponse` type and their 400, 404, and 409
responses with `rig::result` and `rig::error`; these appear in the generated
OpenAPI document and are returned by the generated HTTP dispatcher.
Invalid path integers and JSON bodies produce RIG's documented
`invalid_request` response before a game operation runs.

The sample contract now has left/stay/right actions, player lives and shove
cooldowns, falling obstacles, and a waiting/running/finished game status. A
winner is `null` until the game ends. Both players start with three lives and
the same movement speed and shove cooldown. Obstacles appear every five ticks;
the game runs at about 30 ticks per second after each player submits an action.
When either player loses a life, both return to their starting positions.
The most recent action remains in effect until that player sends another.
`POST /games` starts a fresh game. Optional `width` and `height` query parameters
set the arena to 8–80 columns and 6–40 rows; omitting either uses 20 or 12.
RIG reflects these parameters into OpenAPI, and its generated dispatcher decodes
them before calling the game.

Install RIG, then from this directory run `make server`. Use either player endpoint:

```sh
curl http://127.0.0.1:8765/games/1
curl http://127.0.0.1:8765/openapi.json
curl -X POST 'http://127.0.0.1:8765/games?width=32&height=16'
curl -X POST http://127.0.0.1:8765/games/1/players/1/actions \
  -H 'Content-Type: application/json' -d '{"move":"Right","shove":false}'
curl -X POST http://127.0.0.1:8765/games/1/players/2/actions \
  -H 'Content-Type: application/json' -d '{"move":"Left","shove":false}'
```

For a playable match, run `make play` in a terminal. It starts the server, a
Python bot using the client generated from OpenAPI, and a terminal client for
the human player. The first run installs the pinned client tools in an ignored
virtual environment under `build/`.
Use `make play PLAY_ARGS='--width 32 --height 16'` to choose the arena size.
The launcher creates the game through the generated client before play begins.

Use A/D or the arrow keys to move, Space to shove, and Q to quit. Hold a
movement key to keep moving; the most recent key is applied for one client
update (about three simulation ticks). Restart `make play` for a new game.

Every tenth of a second, the bot reads the game state through generated Python
models, compares left/stay/right against the next few obstacle positions, and
sends its action over HTTP. It sees the same state and has the
same movement and shove rules as the human client. It alternates between
chasing, retreating, and patrolling independently of the human, while dodging
imminent obstacles first. After `make check` or
`make play` generates the client, `build/client-venv/bin/python bot.py`
can also connect to a separately running `make server` instance.

The demo hosts one game (`id` 1), which `POST /games` resets. The HTTP listener
is intentionally limited to localhost and basic JSON requests.
`GET /openapi.json` serves the generated contract embedded in the server binary.
