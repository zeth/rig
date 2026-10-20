#include "build/dodger_json.hpp"

#include <cassert>
#include <stdexcept>

int main() {
    const dodger::GameState state{
        1, 2, 20, 12, dodger::GameStatus::Running,
        {5, 3, 0}, {14, 2, 4}, {{3, 7, 1}}, std::nullopt,
    };
    const auto encoded = rig_json::encode(state);
    assert(encoded["status"] == "Running");
    assert(encoded["winner"].is_null());
    assert(rig_json::encode(rig_json::decode<dodger::GameState>(encoded)) == encoded);

    const auto with_winner = rig_json::encode(dodger::GameState{
        1, 3, 20, 12, dodger::GameStatus::Finished,
        {5, 0, 0}, {14, 2, 4}, {}, dodger::Winner::Bot,
    });
    assert(with_winner["winner"] == "Bot");
    assert(rig_json::encode(rig_json::decode<dodger::GameState>(with_winner)) == with_winner);

    const auto action = rig_json::decode<dodger::Action>(
        nlohmann::json{{"move", "Left"}, {"shove", true}});
    assert(action.move == dodger::Move::Left && action.shove);

    for (const auto& invalid : {
             nlohmann::json{{"move", "Jump"}, {"shove", false}},
             nlohmann::json{{"move", "Left"}},
             nlohmann::json{{"move", "Left"}, {"shove", false}, {"extra", 1}},
             nlohmann::json{{"move", "Left"}, {"shove", 1}},
         }) {
        bool rejected = false;
        try {
            (void)rig_json::decode<dodger::Action>(invalid);
        } catch (const std::invalid_argument&) {
            rejected = true;
        }
        assert(rejected);
    }
}
