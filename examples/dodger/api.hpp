#pragma once

#include <rig/route.hpp>
#include <rig/result.hpp>
#include <optional>
#include <string>
#include <vector>

namespace dodger {

inline constexpr int minimum_arena_width = 8;
inline constexpr int maximum_arena_width = 80;
inline constexpr int minimum_arena_height = 6;
inline constexpr int maximum_arena_height = 40;

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

struct ErrorResponse {
    std::string error;
};

using GameLookup = rig::result<GameState, rig::error<404, ErrorResponse>>;
using CreateResult = rig::result<GameState, rig::error<400, ErrorResponse>>;
using ActionResult = rig::result<GameState,
    rig::error<400, ErrorResponse>,
    rig::error<404, ErrorResponse>,
    rig::error<409, ErrorResponse>>;

RIG_ROUTE(POST, "/games")
CreateResult create_game(std::optional<int> width RIG_QUERY RIG_RANGE(minimum_arena_width, maximum_arena_width),
                         std::optional<int> height RIG_QUERY RIG_RANGE(minimum_arena_height, maximum_arena_height));

RIG_ROUTE(GET, "/games/{id}")
GameLookup get_game(int id);

RIG_ROUTE(POST, "/games/{id}/players/2/actions")
ActionResult submit_action(int id, Action action);

RIG_ROUTE(POST, "/games/{id}/players/1/actions")
ActionResult submit_human_action(int id, Action action);

}
