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

For now, `api.hpp` is a sample C++20 API declaration used by RIG's reflection
prototype. `openapi.json` is generated from it. The game and its HTTP server
have not been implemented yet.

The sample contract now has left/stay/right actions, player lives and shove
cooldowns, falling obstacles, and a waiting/running/finished game status. A
winner is `null` until the game ends. These are intended wire shapes; the
simulation rules and response behaviour still need to be implemented.
