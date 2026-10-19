#include <dodger/api.hpp>
#include <rig/inspect.hpp>

#include <iostream>

int main() {
    rig::writer output(std::cout);
    output.add_namespace<^^dodger>();
    output.finish();
}
