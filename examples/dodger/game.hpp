#pragma once

#include "api.hpp"

#include <cstdint>

namespace dodger {

class Game {
public:
    Game(int width = 20, int height = 12);
    const GameState& state() const { return state_; }
    void set_action(int player, Action action);
    void tick();

private:
    GameState state_;
    Action actions_[2]{{Move::Stay, false}, {Move::Stay, false}};
    bool ready_[2]{false, false};
    std::uint32_t random_state_ = 1;
};

// The demo server hosts one game. The engine itself remains instantiable for tests.
Game& game_instance();

} // namespace dodger
