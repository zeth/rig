#pragma once

#include <rig/route.hpp>
#include <string>

namespace left {
struct Result { int value; };
RIG_ROUTE(GET, "/left") Result read();
}

namespace right {
struct Result { std::string value; };
RIG_ROUTE(GET, "/right") Result read();
}

namespace service {
struct Pair {
    left::Result left;
    right::Result right;
};
RIG_ROUTE(POST, "/pairs") Pair echo(Pair pair);
}
