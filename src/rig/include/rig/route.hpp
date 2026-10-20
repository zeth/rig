#pragma once

// Annotation values must have structural types. Fixed arrays keep the
// declaration valid under GCC's experimental C++26 reflection implementation.
#ifdef RIG_GENERATING
namespace rig {
struct route {
    char method[8];
    char path[128];
};
struct query {};
struct range { int minimum; int maximum; };
}
#define RIG_ROUTE(method, path) [[=::rig::route{#method, path}]]
#define RIG_QUERY [[=::rig::query{}]]
#define RIG_RANGE(minimum, maximum) [[=::rig::range{minimum, maximum}]]
#else
#define RIG_ROUTE(method, path)
#define RIG_QUERY
#define RIG_RANGE(minimum, maximum)
#endif
