#include <rig/route.hpp>
#include <rig/result.hpp>

struct Result { int value; };
RIG_ROUTE(GET, "/results")
Result get_result();
RIG_ROUTE(GET, "/results/limited")
Result get_limited(int limit RIG_QUERY RIG_RANGE(1, 20));

static_assert(sizeof(Result) == sizeof(int));
