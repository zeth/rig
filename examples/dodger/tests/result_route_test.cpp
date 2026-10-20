#include "game.hpp"
#include "build/dodger_routes.hpp"

#include <cassert>

int main() {
    const auto oversized = rig_http::dispatch("GET", "/games/999999999999999999999", "");
    assert(oversized && oversized->status == 400);
    assert(oversized->body["code"] == "invalid_request");

    auto& game = dodger::game_instance();
    game.set_action(1, {dodger::Move::Stay, false});
    game.set_action(2, {dodger::Move::Stay, false});
    for (int i = 0; i < 5000 && game.state().status != dodger::GameStatus::Finished; ++i)
        game.tick();
    assert(game.state().status == dodger::GameStatus::Finished);

    const auto response = rig_http::dispatch(
        "POST", "/games/1/players/2/actions", R"({"move":"Stay","shove":false})");
    assert(response && response->status == 409);
    assert(response->body["error"] == "game finished");
}
