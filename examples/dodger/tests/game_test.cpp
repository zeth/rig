#include "game.hpp"

#include <cassert>

int main() {
    dodger::Game game;
    dodger::Game small(8, 6);
    assert(small.state().arena_width == 8 && small.state().arena_height == 6);
    assert(small.state().human.x == 2 && small.state().bot.x == 5);
    assert(game.state().status == dodger::GameStatus::Waiting);
    game.tick();
    assert(game.state().tick == 0);

    game.set_action(1, {dodger::Move::Right, false});
    game.tick();
    assert(game.state().status == dodger::GameStatus::Waiting);
    game.set_action(2, {dodger::Move::Left, false});
    assert(game.state().status == dodger::GameStatus::Running);
    for (int i = 0; i < 4; ++i) game.tick();
    assert(game.state().human.x == 9);
    assert(game.state().bot.x == 10);

    game.set_action(1, {dodger::Move::Stay, true});
    game.set_action(2, {dodger::Move::Stay, false});
    game.tick();
    assert(game.state().bot.x == 11);
    assert(game.state().human.shove_cooldown_ticks > 0);
    assert(game.state().obstacles.size() == 1);

    // Repeated ticks advance obstacles, resolve hits, and eventually end the match.
    for (int i = 0; i < 5000 && game.state().status != dodger::GameStatus::Finished; ++i)
        game.tick();
    assert(game.state().status == dodger::GameStatus::Finished);
    assert(game.state().winner.has_value());
}
