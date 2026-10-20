#include "game.hpp"

#include <algorithm>
#include <cstdlib>
#include <stdexcept>

namespace dodger {
namespace {

constexpr int kLives = 3;
constexpr int kCooldown = 15;

constexpr int human_start(int width) { return width / 4; }
constexpr int bot_start(int width) { return width - 1 - width / 4; }

int direction(Move move) {
    switch (move) {
    case Move::Left: return -1;
    case Move::Stay: return 0;
    case Move::Right: return 1;
    }
    throw std::invalid_argument("invalid movement");
}

} // namespace

Game::Game(int width, int height)
    : state_{1, 0, width, height, GameStatus::Waiting,
             {human_start(width), kLives, 0}, {bot_start(width), kLives, 0},
             {}, std::nullopt} {
    if (width < minimum_arena_width || width > maximum_arena_width ||
        height < minimum_arena_height || height > maximum_arena_height)
        throw std::invalid_argument("arena width must be 8 to 80 and height 6 to 40");
}

void Game::set_action(int player, Action action) {
    if (player < 1 || player > 2) throw std::out_of_range("unknown player");
    if (state_.status == GameStatus::Finished) throw std::logic_error("game finished");
    direction(action.move);
    actions_[player - 1] = action;
    ready_[player - 1] = true;
    if (ready_[0] && ready_[1]) state_.status = GameStatus::Running;
}

void Game::tick() {
    if (state_.status != GameStatus::Running) return;
    ++state_.tick;

    Player* players[2]{&state_.human, &state_.bot};
    for (int i = 0; i < 2; ++i) {
        auto& player = *players[i];
        player.x = std::clamp(player.x + direction(actions_[i].move),
                              0, state_.arena_width - 1);
        if (player.shove_cooldown_ticks > 0) --player.shove_cooldown_ticks;
    }

    // Each player has the same shove range and cooldown. Simultaneous shoves
    // resolve in player order for this small deterministic prototype.
    for (int i = 0; i < 2; ++i) {
        auto& attacker = *players[i];
        auto& target = *players[1 - i];
        if (actions_[i].shove && attacker.shove_cooldown_ticks == 0 &&
            std::abs(attacker.x - target.x) <= 1) {
            const int push = attacker.x <= target.x ? 1 : -1;
            target.x = std::clamp(target.x + push, 0, state_.arena_width - 1);
            attacker.shove_cooldown_ticks = kCooldown;
        }
    }

    for (auto& obstacle : state_.obstacles) ++obstacle.y;
    bool lost_life = false;
    for (const auto& obstacle : state_.obstacles) {
        if (obstacle.y == state_.arena_height - 1) {
            for (auto* player : players) {
                if (player->x >= obstacle.x && player->x < obstacle.x + obstacle.width) {
                    --player->lives;
                    lost_life = true;
                }
            }
        }
    }
    if (lost_life) {
        state_.human.x = human_start(state_.arena_width);
        state_.bot.x = bot_start(state_.arena_width);
    }
    std::erase_if(state_.obstacles, [this](const Obstacle& obstacle) {
        return obstacle.y >= state_.arena_height - 1;
    });

    if (state_.tick % 5 == 0) {
        random_state_ = random_state_ * 1664525u + 1013904223u;
        const int x = static_cast<int>(random_state_ % state_.arena_width);
        state_.obstacles.push_back({x, 0, 1});
    }

    if (state_.human.lives <= 0 || state_.bot.lives <= 0) {
        state_.status = GameStatus::Finished;
        state_.winner = state_.human.lives <= 0
            ? (state_.bot.lives <= 0 ? Winner::Draw : Winner::Bot)
            : Winner::Human;
    }
}

Game& game_instance() {
    static Game game;
    return game;
}

CreateResult create_game(std::optional<int> width, std::optional<int> height) {
    try {
        game_instance() = Game(width.value_or(20), height.value_or(12));
        return game_instance().state();
    } catch (const std::invalid_argument& error) {
        return rig::error<400, ErrorResponse>{{error.what()}};
    }
}

GameLookup get_game(int id) {
    if (id != 1) return rig::error<404, ErrorResponse>{{"unknown game"}};
    return game_instance().state();
}

namespace {
ActionResult apply_action(int id, int player, Action action) {
    if (id != 1) return rig::error<404, ErrorResponse>{{"unknown game"}};
    try {
        game_instance().set_action(player, action);
        return game_instance().state();
    } catch (const std::invalid_argument& error) {
        return rig::error<400, ErrorResponse>{{error.what()}};
    } catch (const std::logic_error& error) {
        return rig::error<409, ErrorResponse>{{error.what()}};
    }
}
} // namespace

ActionResult submit_action(int id, Action action) {
    return apply_action(id, 2, action);
}

ActionResult submit_human_action(int id, Action action) {
    return apply_action(id, 1, action);
}

} // namespace dodger
