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

    const auto invalid_query = rig_http::dispatch("POST", "/games?width=no", "");
    assert(invalid_query && invalid_query->status == 400);
    assert(invalid_query->body["code"] == "invalid_request");
    const auto invalid_size = rig_http::dispatch("POST", "/games?width=7", "");
    assert(invalid_size && invalid_size->status == 400);
    assert(invalid_size->body["error"].is_string());
    const auto invalid_height = rig_http::dispatch("POST", "/games?height=41", "");
    assert(invalid_height && invalid_height->status == 400);
    assert(invalid_height->body["error"].is_string());
    const auto created = rig_http::dispatch("POST", "/games?width=12&height=8", "");
    assert(created && created->status == 200);
    assert(created->body["arena_width"] == 12 && created->body["arena_height"] == 8);
    assert(created->body["status"] == "Waiting" && created->body["tick"] == 0);
}
