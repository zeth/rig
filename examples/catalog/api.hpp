#pragma once

#include <rig/route.hpp>

#include <optional>
#include <string>
#include <vector>

namespace catalog {

enum class Availability { InStock, BackOrder };

struct Item {
    int id;
    std::string name;
    Availability availability;
    std::optional<std::string> note;
};

struct ItemList {
    std::vector<Item> items;
};

RIG_ROUTE(GET, "/items/{id}")
Item get_item(int id);

RIG_ROUTE(GET, "/items")
ItemList list_items();

RIG_ROUTE(POST, "/items")
Item create_item(Item item);

} // namespace catalog
