#include <rig/route.hpp>
#include <rig/result.hpp>

struct Result { int value; };
RIG_ROUTE(GET, "/results")
Result get_result();
RIG_ROUTE(GET, "/results/limited")
Result get_limited(int limit RIG_QUERY RIG_RANGE(1, 20));
struct Missing {};
struct RIG_VALIDATION_ERROR(Result, "Bad request")
    RIG_UNAUTHORIZED(Result, "Unauthorized")
    RIG_INTERNAL_ERROR(Result, "Internal server error")
    RIG_METHOD_NOT_ALLOWED(Result, "Method not allowed") Service {};
RIG_ROUTE(GET, "/ping") RIG_PUBLIC Result ping();
RIG_ROUTE(GET, "/results/{id}")
RIG_ERROR_RESPONSE(404, Result, "Not found", Missing)
Result get_by_id(int id);

static_assert(sizeof(Result) == sizeof(int));
