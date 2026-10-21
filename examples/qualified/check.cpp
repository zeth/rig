#include "api.hpp"
#include "build/routes.hpp"

#include <cassert>
#include <stdexcept>

left::Result left::read() { return {7}; }
left::Result left::by_key(std::string key) { return {static_cast<int>(key.size())}; }
left::Result left::newest() { return {99}; }
left::Result left::limited(int limit) { return {limit}; }
left::Result left::query(std::string text, bool enabled) {
    const int value = text == "a b" ? 1 : text == "a&b" ? 2 : 0;
    return {enabled ? value : -value};
}
left::Result left::filter(std::optional<int> limit, std::optional<bool> enabled,
                          std::optional<std::string> text) {
    int value = limit.value_or(0);
    if (enabled) value += *enabled ? 100 : 200;
    if (text) value += *text == "a b" ? 1000 : 2000;
    return {value};
}
left::Result left::choices(std::optional<int> selected) { return {selected.value_or(-1)}; }
right::Result right::read() { return {"seven"}; }
service::Pair service::echo(Pair pair) { return pair; }
rig::result<service::Pair, rig::error<422, left::Result>, rig::error<503, right::Result>>
service::check(Pair pair) {
    if (pair.left.value < 0) throw std::invalid_argument("application failure");
    if (pair.left.value == 0) return rig::error<422, left::Result>{pair.left};
    if (pair.right.value.empty()) return rig::error<503, right::Result>{pair.right};
    return pair;
}
left::Result service::lookup(std::string key) {
    if (key == "gone") throw Gone("gone away");
    if (key == "missing") throw Missing("no such key");
    if (key == "range") throw std::out_of_range("outside the table");
    if (key == "broken") throw std::logic_error("broken table");
    if (key == "unmapped") throw 7;
    return {static_cast<int>(key.size())};
}
service::Failure service::rig_error_body(std::type_identity<Failure>, int status,
                                         const std::exception& error) {
    return {status, error.what()};
}

int main() {
    const auto left = rig_http::dispatch("GET", "/left", "");
    const auto literal = rig_http::dispatch("GET", "/left/new", "");
    const auto variable = rig_http::dispatch("GET", "/left/other", "");
    const auto literal_with_query = rig_http::dispatch("GET", "/left/new?view=short", "");
    const auto encoded_variable = rig_http::dispatch("GET", "/left/a%20b?view=short", "");
    const auto encoded_slash = rig_http::dispatch("GET", "/left/a%2Fb", "");
    const auto invalid_escape = rig_http::dispatch("GET", "/left/a%2", "");
    const auto invalid_hex = rig_http::dispatch("GET", "/left/a%GG", "");
    const auto limited = rig_http::dispatch("GET", "/left/limited?limit=12", "");
    const auto missing_limit = rig_http::dispatch("GET", "/left/limited", "");
    const auto invalid_limit = rig_http::dispatch("GET", "/left/limited?limit=no", "");
    const auto oversized_limit = rig_http::dispatch("GET", "/left/limited?limit=999999999999", "");
    const auto duplicate_limit = rig_http::dispatch("GET", "/left/limited?limit=1&limit=2", "");
    const auto escaped_limit = rig_http::dispatch("GET", "/left/limited?li%6dit=10", "");
    const auto malformed_query = rig_http::dispatch("GET", "/left/limited?limit=%XX", "");
    const auto query_text = rig_http::dispatch("GET", "/left/query?text=a+b&enabled=true", "");
    const auto query_false = rig_http::dispatch("GET", "/left/query?text=a%26b&enabled=false", "");
    const auto invalid_bool = rig_http::dispatch("GET", "/left/query?text=a&enabled=yes", "");
    const auto filter_omitted = rig_http::dispatch("GET", "/left/filter", "");
    const auto filter_supplied = rig_http::dispatch(
        "GET", "/left/filter?limit=7&enabled=false&text=a+b", "");
    const auto filter_empty_text = rig_http::dispatch("GET", "/left/filter?text=", "");
    const auto filter_invalid = rig_http::dispatch("GET", "/left/filter?limit=no", "");
    const auto filter_bad_bool = rig_http::dispatch("GET", "/left/filter?enabled=yes", "");
    const auto choices_omitted = rig_http::dispatch("GET", "/left/choices", "");
    const auto choices_one = rig_http::dispatch("GET", "/left/choices?selected=1", "");
    const auto choices_invalid = rig_http::dispatch("GET", "/left/choices?selected=2", "");
    const auto right = rig_http::dispatch("GET", "/right", "");
    const auto pair = rig_http::dispatch(
        "POST", "/pairs", R"({"left":{"value":7},"right":{"value":"seven"}})");
    const auto checked = rig_http::dispatch(
        "POST", "/checked", R"({"left":{"value":7},"right":{"value":"seven"}})");
    const auto left_error = rig_http::dispatch(
        "POST", "/checked", R"({"left":{"value":0},"right":{"value":"seven"}})");
    const auto right_error = rig_http::dispatch(
        "POST", "/checked", R"({"left":{"value":7},"right":{"value":""}})");
    const auto invalid_body = rig_http::dispatch("POST", "/checked", "{");
    assert(left && left->status == 200 && left->body["value"] == 7);
    assert(literal && literal->status == 200 && literal->body["value"] == 99);
    assert(variable && variable->status == 200 && variable->body["value"] == 5);
    assert(literal_with_query && literal_with_query->status == 200 &&
           literal_with_query->body["value"] == 99);
    assert(encoded_variable && encoded_variable->status == 200 &&
           encoded_variable->body["value"] == 3);
    assert(encoded_slash && encoded_slash->status == 200 &&
           encoded_slash->body["value"] == 3);
    assert(invalid_escape && invalid_escape->status == 400 &&
           invalid_escape->body["code"] == "invalid_request");
    assert(invalid_hex && invalid_hex->status == 400 &&
           invalid_hex->body["code"] == "invalid_request");
    assert(limited && limited->status == 200 && limited->body["value"] == 12);
    assert(escaped_limit && escaped_limit->status == 200 && escaped_limit->body["value"] == 10);
    for (const auto& response : {missing_limit, invalid_limit, oversized_limit,
                                 duplicate_limit, malformed_query}) {
        assert(response && response->status == 400 &&
               response->body["code"] == "invalid_request");
    }
    assert(query_text && query_text->status == 200 && query_text->body["value"] == 1);
    assert(query_false && query_false->status == 200 && query_false->body["value"] == -2);
    assert(invalid_bool && invalid_bool->status == 400 &&
           invalid_bool->body["code"] == "invalid_request");
    assert(filter_omitted && filter_omitted->status == 200 &&
           filter_omitted->body["value"] == 0);
    assert(filter_supplied && filter_supplied->status == 200 &&
           filter_supplied->body["value"] == 1207);
    assert(filter_empty_text && filter_empty_text->status == 200 &&
           filter_empty_text->body["value"] == 2000);
    assert(filter_invalid && filter_invalid->status == 400 &&
           filter_invalid->body["code"] == "invalid_request");
    assert(filter_bad_bool && filter_bad_bool->status == 400 &&
           filter_bad_bool->body["code"] == "invalid_request");
    assert(choices_omitted && choices_omitted->status == 200 &&
           choices_omitted->body["value"] == -1);
    assert(choices_one && choices_one->status == 200 && choices_one->body["value"] == 1);
    assert(choices_invalid && choices_invalid->status == 400 &&
           choices_invalid->body["code"] == "invalid_request");
    assert(right && right->status == 200 && right->body["value"] == "seven");
    assert(pair && pair->status == 200 && pair->body["left"]["value"] == 7 &&
           pair->body["right"]["value"] == "seven");
    assert(checked && checked->status == 200 && checked->body["left"]["value"] == 7);
    assert(left_error && left_error->status == 422 && left_error->body["value"] == 0);
    assert(right_error && right_error->status == 503 && right_error->body["value"] == "");
    assert(invalid_body && invalid_body->status == 400 &&
           invalid_body->body["code"] == "invalid_request");
    const auto found = rig_http::dispatch("GET", "/lookup/key", "");
    const auto gone = rig_http::dispatch("GET", "/lookup/gone", "");
    const auto missing = rig_http::dispatch("GET", "/lookup/missing", "");
    const auto range = rig_http::dispatch("GET", "/lookup/range", "");
    const auto broken = rig_http::dispatch("GET", "/lookup/broken", "");
    assert(found && found->status == 200 && found->body["value"] == 3);
    assert(gone && gone->status == 410 && gone->body["status"] == 410 &&
           gone->body["message"] == "gone away" && gone->operation == "lookup");
    assert(missing && missing->status == 404 && missing->body["message"] == "no such key");
    assert(range && range->status == 404 && range->body["message"] == "outside the table");
    assert(broken && broken->status == 500 && broken->body["message"] == "broken table");
    bool unmapped_failure = false;
    try {
        rig_http::dispatch("GET", "/lookup/unmapped", "");
    } catch (int) {
        unmapped_failure = true;
    }
    assert(unmapped_failure);
    bool application_failure = false;
    try {
        rig_http::dispatch("POST", "/checked",
                           R"({"left":{"value":-1},"right":{"value":"seven"}})");
    } catch (const std::invalid_argument&) {
        application_failure = true;
    }
    assert(application_failure);
}
