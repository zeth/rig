#pragma once

#include <rig/route.hpp>
#include <rig/result.hpp>
#include <exception>
#include <optional>
#include <stdexcept>
#include <string>
#include <type_traits>

namespace left {
struct Result { int value; };
RIG_ROUTE(GET, "/left") Result read();
RIG_ROUTE(GET, "/left/{key}") Result by_key(std::string key);
RIG_ROUTE(GET, "/left/new") Result newest();
RIG_ROUTE(GET, "/left/limited") Result limited(int limit RIG_QUERY);
RIG_ROUTE(GET, "/left/query") Result query(std::string text RIG_QUERY, bool enabled RIG_QUERY);
RIG_ROUTE(GET, "/left/filter") Result filter(std::optional<int> limit RIG_QUERY,
                                              std::optional<bool> enabled RIG_QUERY,
                                              std::optional<std::string> text RIG_QUERY);
RIG_ROUTE(GET, "/left/choices") Result choices(
    std::optional<int> selected RIG_QUERY RIG_INT_VALUES(0, 1)
        RIG_PARAMETER_DESCRIPTION("Choose zero or one"));
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

struct Failure { int status; std::string message; };
struct Missing : std::runtime_error { using std::runtime_error::runtime_error; };
struct Gone : Missing { using Missing::Missing; };
// Gone derives from Missing, so it is listed first.
RIG_ROUTE(GET, "/lookup/{key}")
RIG_ERROR_RESPONSE(410, Failure, "Gone", Gone)
RIG_ERROR_RESPONSE(404, Failure, "Not found", Missing, std::out_of_range)
RIG_ERROR_RESPONSE(500, Failure, "Failed", std::exception)
left::Result lookup(std::string key);
Failure rig_error_body(std::type_identity<Failure>, int status, const std::exception& error);
}
