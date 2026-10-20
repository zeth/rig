#pragma once

#include <rig/route.hpp>
#include <rig/result.hpp>
#include <string>

namespace left {
struct Result { int value; };
RIG_ROUTE(GET, "/left") Result read();
RIG_ROUTE(GET, "/left/{key}") Result by_key(std::string key);
RIG_ROUTE(GET, "/left/new") Result newest();
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
RIG_ROUTE(POST, "/checked")
rig::result<Pair, rig::error<422, left::Result>, rig::error<503, right::Result>>
check(Pair pair);
}
