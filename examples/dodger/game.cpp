#include "game.hpp"

#include <algorithm>
#include <cstdlib>
#include <stdexcept>

namespace dodger {
namespace {

constexpr int kLives = 3;
constexpr int kCooldown = 15;

int direction(Move move) {
    switch (move) {
    case Move::Left: return -1;
    case Move::Stay: return 0;
    case Move::Right: return 1;
    }
    throw std::invalid_argument("invalid movement");
}

} // namespace

Game::Game()
    : state_{1, 0, 20, 12, GameStatus::Waiting,
             {5, kLives, 0}, {14, kLives, 0}, {}, std::nullopt} {}

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
    for (const auto& obstacle : state_.obstacles) {
        if (obstacle.y == state_.arena_height - 1) {
            for (auto* player : players) {
                if (player->x >= obstacle.x && player->x < obstacle.x + obstacle.width)
                    --player->lives;
            }
        }
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

GameState get_game(int id) {
    if (id != 1) throw std::out_of_range("unknown game");
    return game_instance().state();
}

GameState submit_action(int id, Action action) {
    if (id != 1) throw std::out_of_range("unknown game");
    game_instance().set_action(2, action);
    return game_instance().state();
}

GameState submit_human_action(int id, Action action) {
    if (id != 1) throw std::out_of_range("unknown game");
    game_instance().set_action(1, action);
    return game_instance().state();
}

} // namespace dodger
