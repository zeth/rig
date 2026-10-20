#include <rig/route.hpp>

struct Result { int value; };
RIG_ROUTE(GET, "/results")
Result get_result();

static_assert(sizeof(Result) == sizeof(int));
