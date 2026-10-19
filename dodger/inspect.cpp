#include <dodger/api.hpp>
#include <rig/inspect.hpp>

#include <iostream>

int main() {
    rig::writer output(std::cout);
    output.add_type<^^dodger::Move>();
    output.add_type<^^dodger::GameStatus>();
    output.add_type<^^dodger::Winner>();
    output.add_type<^^dodger::Player>();
    output.add_type<^^dodger::Obstacle>();
    output.add_type<^^dodger::Action>();
    output.add_type<^^dodger::GameState>();
    output.add_operation<^^dodger::get_game>();
    output.add_operation<^^dodger::submit_action>();
    output.add_operation<^^dodger::submit_human_action>();
    output.finish();
}
