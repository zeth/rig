#include "api.hpp"
#include "build/routes.hpp"

#include <cassert>

left::Result left::read() { return {7}; }
left::Result left::by_key(std::string key) { return {static_cast<int>(key.size())}; }
left::Result left::newest() { return {99}; }
right::Result right::read() { return {"seven"}; }
service::Pair service::echo(Pair pair) { return pair; }

int main() {
    const auto left = rig_http::dispatch("GET", "/left", "");
    const auto literal = rig_http::dispatch("GET", "/left/new", "");
    const auto variable = rig_http::dispatch("GET", "/left/other", "");
    const auto right = rig_http::dispatch("GET", "/right", "");
    const auto pair = rig_http::dispatch(
        "POST", "/pairs", R"({"left":{"value":7},"right":{"value":"seven"}})");
    assert(left && (*left)["value"] == 7);
    assert(literal && (*literal)["value"] == 99);
    assert(variable && (*variable)["value"] == 5);
    assert(right && (*right)["value"] == "seven");
    assert(pair && (*pair)["left"]["value"] == 7 &&
           (*pair)["right"]["value"] == "seven");
}
