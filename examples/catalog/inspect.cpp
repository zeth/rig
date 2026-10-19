#include <examples/catalog/api.hpp>
#include <rig/inspect.hpp>

#include <iostream>

int main() {
    rig::writer output(std::cout);
    output.add_type<^^catalog::Availability>();
    output.add_type<^^catalog::Item>();
    output.add_type<^^catalog::ItemList>();
    output.add_operation<^^catalog::get_item>();
    output.add_operation<^^catalog::list_items>();
    output.add_operation<^^catalog::create_item>();
    output.finish();
}
