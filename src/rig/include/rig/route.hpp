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
struct open_record {};
struct api { char title[128]; char version[32]; };
struct server { char url[256]; };
struct bearer_auth { char name[64]; char format[64]; };
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
#define RIG_OPEN_RECORD [[=::rig::open_record{}]]
#define RIG_API(title, version) [[=::rig::api{title, version}]]
#define RIG_SERVER(url) [[=::rig::server{url}]]
#define RIG_BEARER_AUTH(name, format) [[=::rig::bearer_auth{name, format}]]
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
#define RIG_OPEN_RECORD
#define RIG_API(title, version)
#define RIG_SERVER(url)
#define RIG_BEARER_AUTH(name, format)
#define RIG_ERROR_RESPONSE(status, body, description)
#endif
