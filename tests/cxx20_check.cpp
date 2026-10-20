#include <rig/route.hpp>
#include <rig/result.hpp>

struct Result { int value; };
RIG_ROUTE(GET, "/results")
Result get_result();
RIG_ROUTE(GET, "/results/limited")
Result get_limited(int limit RIG_QUERY);

static_assert(sizeof(Result) == sizeof(int));
