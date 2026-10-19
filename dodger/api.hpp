#pragma once

#include <rig/route.hpp>
#include <optional>
#include <vector>

namespace dodger {

enum class Move { Left, Stay, Right };
enum class GameStatus { Waiting, Running, Finished };
enum class Winner { Human, Bot, Draw };

struct Player {
    int x;
    int lives;
    int shove_cooldown_ticks;
};

struct Obstacle {
    int x;
    int y;
    int width;
};

struct Action {
    Move move;
    bool shove;
};

struct GameState {
    int id;
    int tick;
    int arena_width;
    int arena_height;
    GameStatus status;
    Player human;
    Player bot;
    std::vector<Obstacle> obstacles;
    std::optional<Winner> winner;
};

RIG_ROUTE(GET, "/games/{id}")
GameState get_game(int id);

RIG_ROUTE(POST, "/games/{id}/players/2/actions")
GameState submit_action(int id, Action action);

}
