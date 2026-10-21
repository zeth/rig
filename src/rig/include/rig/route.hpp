#pragma once

// Annotation values must have structural types. Fixed arrays keep the
// declaration valid under GCC's experimental C++26 reflection implementation.
#ifdef RIG_GENERATING
#include <cstddef>
#include <initializer_list>
#include <meta>
#include <string_view>
namespace rig {
struct route {
    char method[8];
    char path[128];
};
struct query {};
struct context {};
struct range { int minimum; int maximum; };
struct int_values { int values[16]; int count; };
template <int... Values>
consteval int_values make_int_values() {
    static_assert(sizeof...(Values) > 0 && sizeof...(Values) <= 16,
                  "RIG integer choices require one to sixteen values");
    return {{Values...}, static_cast<int>(sizeof...(Values))};
}
struct string_values { char values[16][64]{}; int count = 0; };
consteval string_values make_string_values(std::initializer_list<std::string_view> values) {
    if (values.size() == 0 || values.size() > 16)
        throw "RIG string choices require one to sixteen values";
    string_values result{};
    for (auto value : values) {
        if (value.empty() || value.size() >= 64)
            throw "RIG string choices must contain one to 63 characters";
        for (std::size_t index = 0; index < value.size(); ++index)
            result.values[result.count][index] = value[index];
        ++result.count;
    }
    return result;
}
struct parameter_description { char text[512]; };
struct minimum { int value; };
struct field_description { char text[256]; };
struct omit_empty {};
struct nullable {};
struct summary { char text[256]; };
struct description { char text[2048]; };
struct response_description { char text[256]; };
struct bool_value { bool value; };
struct open_record {};
struct inline_record {};
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
#define RIG_CONTEXT [[=::rig::context{}]]
#define RIG_RANGE(minimum, maximum) [[=::rig::range{minimum, maximum}]]
#define RIG_INT_VALUES(...) [[=::rig::make_int_values<__VA_ARGS__>()]]
#define RIG_STRING_VALUES(...) [[=::rig::make_string_values({__VA_ARGS__})]]
#define RIG_PARAMETER_DESCRIPTION(text) [[=::rig::parameter_description{text}]]
#define RIG_MINIMUM(value) [[=::rig::minimum{value}]]
#define RIG_FIELD_DESCRIPTION(text) [[=::rig::field_description{text}]]
#define RIG_OMIT_EMPTY [[=::rig::omit_empty{}]]
#define RIG_NULLABLE [[=::rig::nullable{}]]
#define RIG_SUMMARY(text) [[=::rig::summary{text}]]
#define RIG_DESCRIPTION(text) [[=::rig::description{text}]]
#define RIG_RESPONSE_DESCRIPTION(text) [[=::rig::response_description{text}]]
#define RIG_BOOL_VALUE(value) [[=::rig::bool_value{value}]]
#define RIG_OPEN_RECORD [[=::rig::open_record{}]]
#define RIG_INLINE_RECORD [[=::rig::inline_record{}]]
#define RIG_API(title, version) [[=::rig::api{title, version}]]
#define RIG_SERVER(url) [[=::rig::server{url}]]
#define RIG_BEARER_AUTH(name, format) [[=::rig::bearer_auth{name, format}]]
#define RIG_ERROR_RESPONSE(status, body, description) \
    [[=::rig::error_response{status, ^^body, description}]]
#else
#define RIG_ROUTE(method, path)
#define RIG_QUERY
#define RIG_CONTEXT
#define RIG_RANGE(minimum, maximum)
#define RIG_INT_VALUES(...)
#define RIG_STRING_VALUES(...)
#define RIG_PARAMETER_DESCRIPTION(text)
#define RIG_MINIMUM(value)
#define RIG_FIELD_DESCRIPTION(text)
#define RIG_OMIT_EMPTY
#define RIG_NULLABLE
#define RIG_SUMMARY(text)
#define RIG_DESCRIPTION(text)
#define RIG_RESPONSE_DESCRIPTION(text)
#define RIG_BOOL_VALUE(value)
#define RIG_OPEN_RECORD
#define RIG_INLINE_RECORD
#define RIG_API(title, version)
#define RIG_SERVER(url)
#define RIG_BEARER_AUTH(name, format)
#define RIG_ERROR_RESPONSE(status, body, description)
#endif
