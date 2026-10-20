#pragma once

// Annotation values must have structural types. Fixed arrays keep the
// declaration valid under GCC's experimental C++26 reflection implementation.
#ifdef RIG_GENERATING
namespace rig {
struct route {
    char method[8];
    char path[128];
};
template <typename Body>
struct error_response {
    int status;
};
}
#define RIG_ROUTE(method, path) [[=::rig::route{#method, path}]]
#define RIG_ERROR(status, body) [[=::rig::error_response<body>{status}]]
#else
#define RIG_ROUTE(method, path)
#define RIG_ERROR(status, body)
#endif
