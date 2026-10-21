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
struct min_length { int value; };
struct max_length { int value; };
struct format { char text[32]; };
struct pattern { char text[256]; };
struct value_type {};
// A bool, integer or string default, chosen by the make_default overload.
struct default_value { int kind; long long integer; bool boolean; char text[256]; };
consteval default_value make_default(bool value) { return {1, 0, value, {}}; }
consteval default_value make_default(int value) { return {2, value, false, {}}; }
consteval default_value make_default(long long value) { return {2, value, false, {}}; }
consteval default_value make_default(const char* value) {
    default_value result{3, 0, false, {}};
    std::size_t length = 0;
    while (value[length] != '\0') ++length;
    if (length >= 256) throw "RIG string defaults must be shorter than 256 characters";
    for (std::size_t index = 0; index < length; ++index) result.text[index] = value[index];
    return result;
}
struct field_description { char text[256]; };
struct omit_empty {};
struct nullable {};
struct write_only {};
struct summary { char text[256]; };
struct description { char text[2048]; };
struct response_description { char text[256]; };
struct bool_value { bool value; };
struct open_record {};
struct inline_record {};
struct api { char title[128]; char version[32]; };
struct server { char url[256]; };
struct bearer_auth { char name[64]; char format[64]; };
struct validation_error { std::meta::info body; char description[256]; };
struct unauthorized { std::meta::info body; char description[256]; };
struct internal_error { std::meta::info body; char description[256]; };
struct public_operation {};
struct host_response { char media_type[128]; };
struct success_status { int status; };
struct error_response {
    int status;
    std::meta::info body;
    char description[256];
    std::meta::info exceptions[8];
    int exception_count;
};
template <typename... Exceptions>
consteval error_response make_error_response(int status, std::meta::info body,
                                             std::string_view description) {
    static_assert(sizeof...(Exceptions) <= 8,
                  "RIG error responses map at most eight exception types");
    if (description.size() >= 256)
        throw "RIG error response descriptions must be shorter than 256 characters";
    error_response result{status, body, {}, {^^Exceptions...}, sizeof...(Exceptions)};
    for (std::size_t index = 0; index < description.size(); ++index)
        result.description[index] = description[index];
    return result;
}
}
#define RIG_ROUTE(method, path) [[=::rig::route{#method, path}]]
#define RIG_QUERY [[=::rig::query{}]]
#define RIG_CONTEXT [[=::rig::context{}]]
#define RIG_RANGE(minimum, maximum) [[=::rig::range{minimum, maximum}]]
#define RIG_INT_VALUES(...) [[=::rig::make_int_values<__VA_ARGS__>()]]
#define RIG_STRING_VALUES(...) [[=::rig::make_string_values({__VA_ARGS__})]]
#define RIG_PARAMETER_DESCRIPTION(text) [[=::rig::parameter_description{text}]]
#define RIG_MINIMUM(value) [[=::rig::minimum{value}]]
#define RIG_MIN_LENGTH(value) [[=::rig::min_length{value}]]
#define RIG_MAX_LENGTH(value) [[=::rig::max_length{value}]]
#define RIG_FORMAT(text) [[=::rig::format{text}]]
#define RIG_PATTERN(text) [[=::rig::pattern{text}]]
#define RIG_VALUE_TYPE [[=::rig::value_type{}]]
#define RIG_DEFAULT(value) [[=::rig::make_default(value)]]
#define RIG_FIELD_DESCRIPTION(text) [[=::rig::field_description{text}]]
#define RIG_OMIT_EMPTY [[=::rig::omit_empty{}]]
#define RIG_NULLABLE [[=::rig::nullable{}]]
#define RIG_WRITE_ONLY [[=::rig::write_only{}]]
#define RIG_SUMMARY(text) [[=::rig::summary{text}]]
#define RIG_DESCRIPTION(text) [[=::rig::description{text}]]
#define RIG_RESPONSE_DESCRIPTION(text) [[=::rig::response_description{text}]]
#define RIG_BOOL_VALUE(value) [[=::rig::bool_value{value}]]
#define RIG_OPEN_RECORD [[=::rig::open_record{}]]
#define RIG_INLINE_RECORD [[=::rig::inline_record{}]]
#define RIG_API(title, version) [[=::rig::api{title, version}]]
#define RIG_SERVER(url) [[=::rig::server{url}]]
#define RIG_BEARER_AUTH(name, format) [[=::rig::bearer_auth{name, format}]]
#define RIG_VALIDATION_ERROR(body, description) \
    [[=::rig::validation_error{^^body, description}]]
#define RIG_UNAUTHORIZED(body, description) \
    [[=::rig::unauthorized{^^body, description}]]
#define RIG_PUBLIC [[=::rig::public_operation{}]]
#define RIG_HOST_RESPONSE(media_type) [[=::rig::host_response{media_type}]]
#define RIG_SUCCESS_STATUS(status) [[=::rig::success_status{status}]]
#define RIG_INTERNAL_ERROR(body, description) \
    [[=::rig::internal_error{^^body, description}]]
#define RIG_ERROR_RESPONSE(status, body, description, ...) \
    [[=::rig::make_error_response<__VA_ARGS__>(status, ^^body, description)]]
#else
#define RIG_ROUTE(method, path)
#define RIG_QUERY
#define RIG_CONTEXT
#define RIG_RANGE(minimum, maximum)
#define RIG_INT_VALUES(...)
#define RIG_STRING_VALUES(...)
#define RIG_PARAMETER_DESCRIPTION(text)
#define RIG_MINIMUM(value)
#define RIG_MIN_LENGTH(value)
#define RIG_MAX_LENGTH(value)
#define RIG_FORMAT(text)
#define RIG_PATTERN(text)
#define RIG_VALUE_TYPE
#define RIG_DEFAULT(value)
#define RIG_FIELD_DESCRIPTION(text)
#define RIG_OMIT_EMPTY
#define RIG_NULLABLE
#define RIG_WRITE_ONLY
#define RIG_SUMMARY(text)
#define RIG_DESCRIPTION(text)
#define RIG_RESPONSE_DESCRIPTION(text)
#define RIG_BOOL_VALUE(value)
#define RIG_OPEN_RECORD
#define RIG_INLINE_RECORD
#define RIG_API(title, version)
#define RIG_SERVER(url)
#define RIG_BEARER_AUTH(name, format)
#define RIG_VALIDATION_ERROR(body, description)
#define RIG_UNAUTHORIZED(body, description)
#define RIG_PUBLIC
#define RIG_HOST_RESPONSE(media_type)
#define RIG_SUCCESS_STATUS(status)
#define RIG_INTERNAL_ERROR(body, description)
#define RIG_ERROR_RESPONSE(status, body, description, ...)
#endif
