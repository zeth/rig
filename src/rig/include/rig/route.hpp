#pragma once

// Annotation values must have structural types. Fixed arrays keep the
// declaration valid under GCC's experimental C++26 reflection implementation.
#ifdef RIG_GENERATING
#include <meta>
namespace rig {
struct route {
    char method[8];
    char path[128];
};
struct query {};
struct range { int minimum; int maximum; };
struct summary { char text[256]; };
struct description { char text[2048]; };
struct response_description { char text[256]; };
struct bool_value { bool value; };
struct error_response {
    int status;
    std::meta::info body;
    char description[256];
};
}
#define RIG_ROUTE(method, path) [[=::rig::route{#method, path}]]
#define RIG_QUERY [[=::rig::query{}]]
#define RIG_RANGE(minimum, maximum) [[=::rig::range{minimum, maximum}]]
#define RIG_SUMMARY(text) [[=::rig::summary{text}]]
#define RIG_DESCRIPTION(text) [[=::rig::description{text}]]
#define RIG_RESPONSE_DESCRIPTION(text) [[=::rig::response_description{text}]]
#define RIG_BOOL_VALUE(value) [[=::rig::bool_value{value}]]
#define RIG_ERROR_RESPONSE(status, body, description) \
    [[=::rig::error_response{status, ^^body, description}]]
#else
#define RIG_ROUTE(method, path)
#define RIG_QUERY
#define RIG_RANGE(minimum, maximum)
#define RIG_SUMMARY(text)
#define RIG_DESCRIPTION(text)
#define RIG_RESPONSE_DESCRIPTION(text)
#define RIG_BOOL_VALUE(value)
#define RIG_ERROR_RESPONSE(status, body, description)
#endif
