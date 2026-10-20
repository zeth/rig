#include "api.hpp"
#include <rig/inspect.hpp>
#include <iostream>

int main() {
    rig::writer output(std::cout);
    output.add_type<^^left::Result>();
    output.add_type<^^right::Result>();
    output.add_type<^^service::Pair>();
    output.add_operation<^^left::read>();
    output.add_operation<^^right::read>();
    output.add_operation<^^service::echo>();
    output.finish();
}
