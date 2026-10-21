#include <rig/route.hpp>
#include <rig/result.hpp>

struct Result { int value; };
RIG_ROUTE(GET, "/results")
Result get_result();
RIG_ROUTE(GET, "/results/limited")
Result get_limited(int limit RIG_QUERY RIG_RANGE(1, 20));
struct Missing {};
RIG_ROUTE(GET, "/results/{id}")
RIG_ERROR_RESPONSE(404, Result, "Not found", Missing)
Result get_by_id(int id);

static_assert(sizeof(Result) == sizeof(int));
