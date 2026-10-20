#include "api.hpp"
#include "build/routes.hpp"

#include <cassert>

left::Result left::read() { return {7}; }
left::Result left::by_key(std::string key) { return {static_cast<int>(key.size())}; }
left::Result left::newest() { return {99}; }
right::Result right::read() { return {"seven"}; }
service::Pair service::echo(Pair pair) { return pair; }
rig::result<service::Pair, rig::error<422, left::Result>, rig::error<503, right::Result>>
service::check(Pair pair) {
    if (pair.left.value == 0) return rig::error<422, left::Result>{pair.left};
    if (pair.right.value.empty()) return rig::error<503, right::Result>{pair.right};
    return pair;
}

int main() {
    const auto left = rig_http::dispatch("GET", "/left", "");
    const auto literal = rig_http::dispatch("GET", "/left/new", "");
    const auto variable = rig_http::dispatch("GET", "/left/other", "");
    const auto right = rig_http::dispatch("GET", "/right", "");
    const auto pair = rig_http::dispatch(
        "POST", "/pairs", R"({"left":{"value":7},"right":{"value":"seven"}})");
    const auto checked = rig_http::dispatch(
        "POST", "/checked", R"({"left":{"value":7},"right":{"value":"seven"}})");
    const auto left_error = rig_http::dispatch(
        "POST", "/checked", R"({"left":{"value":0},"right":{"value":"seven"}})");
    const auto right_error = rig_http::dispatch(
        "POST", "/checked", R"({"left":{"value":7},"right":{"value":""}})");
    assert(left && left->status == 200 && left->body["value"] == 7);
    assert(literal && literal->status == 200 && literal->body["value"] == 99);
    assert(variable && variable->status == 200 && variable->body["value"] == 5);
    assert(right && right->status == 200 && right->body["value"] == "seven");
    assert(pair && pair->status == 200 && pair->body["left"]["value"] == 7 &&
           pair->body["right"]["value"] == "seven");
    assert(checked && checked->status == 200 && checked->body["left"]["value"] == 7);
    assert(left_error && left_error->status == 422 && left_error->body["value"] == 0);
    assert(right_error && right_error->status == 503 && right_error->body["value"] == "");
}
