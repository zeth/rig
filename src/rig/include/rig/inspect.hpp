#pragma once

#ifndef RIG_GENERATING
#error "rig/inspect.hpp requires C++26 reflection and RIG_GENERATING"
#endif

#include <rig/route.hpp>
#include <rig/result.hpp>

#include <meta>
#include <array>
#include <cstddef>
#include <map>
#include <ostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>
#include <optional>
#include <variant>

namespace rig {
namespace detail {

consteval bool has_route(std::meta::info member) {
    return std::meta::is_function(member) &&
        !std::meta::annotations_of_with_type(member, ^^rig::route).empty();
}

consteval bool has_service(std::meta::info member) {
    return std::meta::is_type(member) && std::meta::is_class_type(member) &&
        !std::meta::annotations_of_with_type(member, ^^rig::api).empty();
}

consteval bool is_result_type(std::meta::info type) {
    return std::meta::has_template_arguments(type) &&
        std::meta::template_of(type) == ^^rig::result;
}

consteval bool is_success_type(std::meta::info type) {
    return std::meta::has_template_arguments(type) &&
        std::meta::template_of(type) == ^^rig::success;
}

consteval bool is_host_value_type(std::meta::info type) {
    return std::meta::is_same_type(type, ^^rig::host_value);
}

// nlohmann::json, recognised by shape so RIG needs no nlohmann header: a
// basic_json specialisation in namespace nlohmann whose objects are std::map.
consteval bool is_json_object_type(std::meta::info type) {
    if (!std::meta::has_template_arguments(type)) return false;
    const auto templ = std::meta::template_of(type);
    if (!std::meta::has_identifier(templ) || std::meta::identifier_of(templ) != "basic_json")
        return false;
    bool in_nlohmann = false;
    for (auto scope = std::meta::parent_of(templ); scope != ^^::;
         scope = std::meta::parent_of(scope)) {
        if (std::meta::has_identifier(scope) && std::meta::identifier_of(scope) == "nlohmann")
            in_nlohmann = true;
    }
    return in_nlohmann && std::meta::template_arguments_of(type)[0] == ^^std::map;
}

consteval bool is_string_map_type(std::meta::info type) {
    return std::meta::has_template_arguments(type) &&
        std::meta::template_of(type) == ^^std::map &&
        std::meta::is_same_type(std::meta::template_arguments_of(type)[0], ^^std::string);
}

consteval bool contains_type(const std::vector<std::meta::info>& types,
                             std::meta::info type) {
    for (auto existing : types) {
        if (std::meta::is_same_type(existing, type)) return true;
    }
    return false;
}

consteval void collect_type(std::meta::info type, std::vector<std::meta::info>& types) {
    type = std::meta::remove_cvref(type);
    if (std::meta::is_same_type(type, ^^int) ||
        std::meta::is_same_type(type, ^^long long) ||
        std::meta::is_same_type(type, ^^double) ||
        std::meta::is_same_type(type, ^^bool) ||
        std::meta::is_same_type(type, ^^std::string) ||
        is_json_object_type(type)) return;
    if (is_string_map_type(type)) {
        collect_type(std::meta::template_arguments_of(type)[1], types);
        return;
    }

    if (is_success_type(type)) {
        collect_type(std::meta::template_arguments_of(type)[0], types);
        return;
    }

    if (is_host_value_type(type)) return;

    if (is_result_type(type)) {
        const auto arguments = std::meta::template_arguments_of(type);
        collect_type(arguments[0], types);
        for (std::size_t index = 1; index < arguments.size(); ++index) {
            collect_type(std::meta::template_arguments_of(arguments[index])[1], types);
        }
        return;
    }

    if (std::meta::has_template_arguments(type)) {
        const auto templ = std::meta::template_of(type);
        if (templ == ^^std::vector || templ == ^^std::optional) {
            collect_type(std::meta::template_arguments_of(type)[0], types);
        } else if (templ == ^^std::variant) {
            for (auto alternative : std::meta::template_arguments_of(type)) {
                collect_type(alternative, types);
            }
        }
        // Any other specialisation is emitted as unsupported, which validation rejects.
        return;
    }

    if (!std::meta::is_enum_type(type) && !std::meta::is_class_type(type)) return;
    if (contains_type(types, type)) return;
    types.push_back(type);
    if (std::meta::is_class_type(type)) {
        for (auto base : std::meta::bases_of(type, std::meta::access_context::unprivileged())) {
            collect_type(std::meta::type_of(base), types);
        }
        for (auto field : std::meta::nonstatic_data_members_of(
                 type, std::meta::access_context::unprivileged())) {
            collect_type(std::meta::type_of(field), types);
        }
    }
}

consteval std::vector<std::meta::info> reachable_types(std::meta::info scope) {
    std::vector<std::meta::info> types;
    for (auto member : std::meta::members_of(
             scope, std::meta::access_context::unprivileged())) {
        if (has_service(member)) {
            for (auto annotation : std::meta::annotations_of_with_type(
                     member, ^^rig::validation_error)) {
                const auto validation = std::meta::extract<rig::validation_error>(
                    std::meta::constant_of(annotation));
                collect_type(validation.body, types);
            }
            for (auto annotation : std::meta::annotations_of_with_type(
                     member, ^^rig::unauthorized)) {
                const auto response = std::meta::extract<rig::unauthorized>(
                    std::meta::constant_of(annotation));
                collect_type(response.body, types);
            }
            for (auto annotation : std::meta::annotations_of_with_type(
                     member, ^^rig::internal_error)) {
                const auto response = std::meta::extract<rig::internal_error>(
                    std::meta::constant_of(annotation));
                collect_type(response.body, types);
            }
            for (auto annotation : std::meta::annotations_of_with_type(
                     member, ^^rig::method_not_allowed)) {
                const auto response = std::meta::extract<rig::method_not_allowed>(
                    std::meta::constant_of(annotation));
                collect_type(response.body, types);
            }
        }
        if (!has_route(member)) continue;
        collect_type(std::meta::return_type_of(member), types);
        for (auto parameter : std::meta::parameters_of(member)) {
            if (!std::meta::annotations_of_with_type(parameter, ^^rig::context).empty()) continue;
            collect_type(std::meta::type_of(parameter), types);
        }
        for (auto annotation : std::meta::annotations_of_with_type(
                 member, ^^rig::error_response)) {
            const auto response = std::meta::extract<rig::error_response>(
                std::meta::constant_of(annotation));
            collect_type(response.body, types);
        }
        for (auto annotation : std::meta::annotations_of_with_type(member, ^^rig::sse_event)) {
            collect_type(std::meta::extract<rig::sse_event>(std::meta::constant_of(annotation)).body,
                         types);
        }
    }
    // Keep direct namespace types in source order so adding a route does not
    // reorder unrelated schemas. Append any nested or external types after.
    std::vector<std::meta::info> ordered;
    for (auto member : std::meta::members_of(
             scope, std::meta::access_context::unprivileged())) {
        if (std::meta::is_type(member) && contains_type(types, member)) {
            ordered.push_back(member);
        }
    }
    for (auto type : types) {
        if (!contains_type(ordered, type)) ordered.push_back(type);
    }
    return ordered;
}

consteval std::vector<std::meta::info> namespace_types(
    const std::vector<std::meta::info>& scopes) {
    std::vector<std::meta::info> types;
    for (auto scope : scopes) {
        for (auto type : reachable_types(scope)) {
            if (!contains_type(types, type)) types.push_back(type);
        }
    }
    return types;
}

consteval std::vector<std::meta::info> namespace_operations(
    const std::vector<std::meta::info>& scopes) {
    std::vector<std::meta::info> operations;
    for (auto scope : scopes) {
        for (auto member : std::meta::members_of(
                 scope, std::meta::access_context::unprivileged())) {
            if (!has_route(member)) continue;
            bool seen = false;
            for (auto existing : operations) {
                if (existing == member) seen = true;
            }
            if (!seen) operations.push_back(member);
        }
    }
    return operations;
}

consteval std::vector<std::meta::info> namespace_services(
    const std::vector<std::meta::info>& scopes) {
    std::vector<std::meta::info> services;
    for (auto scope : scopes) {
        for (auto member : std::meta::members_of(
                 scope, std::meta::access_context::unprivileged())) {
            if (has_service(member) && !contains_type(services, member)) {
                services.push_back(member);
            }
        }
    }
    return services;
}

inline void quoted(std::ostream& output, std::string_view value) {
    output << '"';
    for (unsigned char ch : value) {
        switch (ch) {
        case '"': output << "\\\""; break;
        case '\\': output << "\\\\"; break;
        case '\n': output << "\\n"; break;
        case '\r': output << "\\r"; break;
        case '\t': output << "\\t"; break;
        default:
            if (ch < 0x20) {
                constexpr char digits[] = "0123456789abcdef";
                output << "\\u00" << digits[ch >> 4] << digits[ch & 15];
            } else {
                output << ch;
            }
        }
    }
    output << '"';
}

template <std::meta::info Entity>
std::string qualified_name() {
    constexpr auto parent = std::meta::parent_of(Entity);
    const auto scope = std::meta::display_string_of(parent);
    const auto name = std::meta::identifier_of(Entity);
    return scope == "::" ? std::string(name) : std::string(scope) + "::" + std::string(name);
}

template <std::meta::info Type>
void emit_type(std::ostream& output) {
    constexpr auto type = std::meta::remove_cvref(Type);
    if constexpr (std::meta::is_same_type(type, ^^int)) {
        output << "{\"kind\":\"builtin\",\"name\":\"int\"}";
    } else if constexpr (std::meta::is_same_type(type, ^^long long)) {
        output << "{\"kind\":\"builtin\",\"name\":\"int64\"}";
    } else if constexpr (std::meta::is_same_type(type, ^^double)) {
        output << "{\"kind\":\"builtin\",\"name\":\"double\"}";
    } else if constexpr (std::meta::is_same_type(type, ^^bool)) {
        output << "{\"kind\":\"builtin\",\"name\":\"bool\"}";
    } else if constexpr (std::meta::is_same_type(type, ^^std::string)) {
        output << "{\"kind\":\"builtin\",\"name\":\"string\"}";
    } else if constexpr (is_json_object_type(type)) {
        output << "{\"kind\":\"builtin\",\"name\":\"object\"}";
    } else if constexpr (is_string_map_type(type)) {
        constexpr auto arguments = std::define_static_array(
            std::meta::template_arguments_of(type));
        output << "{\"kind\":\"map\",\"values\":";
        emit_type<arguments[1]>(output);
        output << '}';
    } else if constexpr (std::meta::has_template_arguments(type)) {
        constexpr auto templ = std::meta::template_of(type);
        if constexpr (templ == ^^std::vector || templ == ^^std::optional) {
            constexpr auto arguments = std::define_static_array(
                std::meta::template_arguments_of(type));
            output << "{\"kind\":\"";
            if constexpr (templ == ^^std::vector) {
                output << "array\",\"items\":";
            } else {
                output << "optional\",\"value\":";
            }
            emit_type<arguments[0]>(output);
            output << '}';
        } else if constexpr (templ == ^^std::variant) {
            output << "{\"kind\":\"variant\",\"alternatives\":[";
            bool first = true;
            template for (constexpr auto alternative : std::define_static_array(
                std::meta::template_arguments_of(type))) {
                if (!first) output << ',';
                first = false;
                emit_type<alternative>(output);
            }
            output << "]}";
        } else {
            // The converter rejects any unregistered specialization.
            output << "{\"kind\":\"unsupported\",\"name\":";
            quoted(output, std::meta::display_string_of(type));
            output << '}';
        }
    } else {
        output << "{\"kind\":\"named\",\"name\":";
        quoted(output, qualified_name<type>());
        output << '}';
    }
}

template <std::meta::info Entity, typename Annotation>
consteval std::size_t annotation_count() {
    return std::meta::annotations_of_with_type(Entity, ^^Annotation).size();
}

// Constraints a record field and an HTTP parameter share. IR validation checks
// that each suits the entity's type.
template <std::meta::info Entity>
void emit_value_constraints(std::ostream& output) {
    static_assert(annotation_count<Entity, rig::format>() <= 1 &&
                  annotation_count<Entity, rig::min_length>() <= 1 &&
                  annotation_count<Entity, rig::max_length>() <= 1 &&
                  annotation_count<Entity, rig::default_value>() <= 1 &&
                  annotation_count<Entity, rig::pattern>() <= 1,
                  "RIG values need at most one of each constraint");
    if constexpr (annotation_count<Entity, rig::format>() == 1) {
        constexpr auto value = [:std::meta::constant_of(
            std::meta::annotations_of_with_type(Entity, ^^rig::format)[0]):];
        output << ",\"format\":";
        quoted(output, value.text);
    }
    if constexpr (annotation_count<Entity, rig::pattern>() == 1) {
        constexpr auto value = [:std::meta::constant_of(
            std::meta::annotations_of_with_type(Entity, ^^rig::pattern)[0]):];
        output << ",\"pattern\":";
        quoted(output, value.text);
    }
    if constexpr (annotation_count<Entity, rig::min_length>() == 1) {
        constexpr auto value = [:std::meta::constant_of(
            std::meta::annotations_of_with_type(Entity, ^^rig::min_length)[0]):];
        output << ",\"min_length\":" << value.value;
    }
    if constexpr (annotation_count<Entity, rig::max_length>() == 1) {
        constexpr auto value = [:std::meta::constant_of(
            std::meta::annotations_of_with_type(Entity, ^^rig::max_length)[0]):];
        output << ",\"max_length\":" << value.value;
    }
    if constexpr (annotation_count<Entity, rig::default_value>() == 1) {
        constexpr auto value = [:std::meta::constant_of(
            std::meta::annotations_of_with_type(Entity, ^^rig::default_value)[0]):];
        output << ",\"default\":";
        if constexpr (value.kind == 1) {
            output << (value.boolean ? "true" : "false");
        } else if constexpr (value.kind == 2) {
            output << value.integer;
        } else {
            quoted(output, value.text);
        }
    }
}

template <std::meta::info Type>
void emit_record(std::ostream& output) {
    output << "{\"kind\":\"record\",\"name\":";
    quoted(output, std::meta::identifier_of(Type));
    output << ",\"cpp_name\":";
    quoted(output, qualified_name<Type>());
    constexpr auto open = std::define_static_array(
        std::meta::annotations_of_with_type(Type, ^^rig::open_record));
    static_assert(open.size() <= 1, "RIG records need at most one open-record annotation");
    if constexpr (open.size() == 1) output << ",\"open\":true";
    constexpr auto inline_records = std::define_static_array(
        std::meta::annotations_of_with_type(Type, ^^rig::inline_record));
    static_assert(inline_records.size() <= 1, "RIG records need at most one inline annotation");
    if constexpr (inline_records.size() == 1) output << ",\"inline\":true";
    if constexpr (annotation_count<Type, rig::value_type>() == 1) output << ",\"value\":true";
    static_assert(annotation_count<Type, rig::min_properties>() <= 1,
                  "RIG records need at most one minimum property count");
    if constexpr (annotation_count<Type, rig::min_properties>() == 1) {
        constexpr auto value = [:std::meta::constant_of(
            std::meta::annotations_of_with_type(Type, ^^rig::min_properties)[0]):];
        output << ",\"min_properties\":" << value.value;
    }
    constexpr auto bases = std::define_static_array(
        std::meta::bases_of(Type, std::meta::access_context::unprivileged()));
    static_assert(bases.size() <= 1, "RIG records extend at most one base record");
    if constexpr (bases.size() == 1) {
        output << ",\"base\":";
        quoted(output, qualified_name<std::meta::type_of(bases[0])>());
    }
    constexpr auto descriptions = std::define_static_array(
        std::meta::annotations_of_with_type(Type, ^^rig::description));
    static_assert(descriptions.size() <= 1, "RIG records need at most one description");
    if constexpr (descriptions.size() == 1) {
        constexpr auto value = [:std::meta::constant_of(descriptions[0]):];
        output << ",\"description\":";
        quoted(output, value.text);
    }
    output << ",\"fields\":[";
    bool first = true;
    template for (constexpr auto field : std::define_static_array(
        std::meta::nonstatic_data_members_of(Type, std::meta::access_context::unprivileged()))) {
        if (!first) output << ',';
        first = false;
        output << "{\"name\":";
        quoted(output, std::meta::identifier_of(field));
        output << ",\"type\":";
        emit_type<std::meta::type_of(field)>(output);
        constexpr auto bool_values = std::define_static_array(
            std::meta::annotations_of_with_type(field, ^^rig::bool_value));
        static_assert(bool_values.size() <= 1, "RIG fields need at most one boolean value");
        if constexpr (bool_values.size() == 1) {
            static_assert(std::meta::is_same_type(std::meta::type_of(field), ^^bool),
                          "RIG_BOOL_VALUE requires a bool field");
            constexpr auto value = [:std::meta::constant_of(bool_values[0]):];
            output << ",\"bool_value\":" << (value.value ? "true" : "false");
        }
        constexpr auto descriptions = std::define_static_array(
            std::meta::annotations_of_with_type(field, ^^rig::field_description));
        static_assert(descriptions.size() <= 1, "RIG fields need at most one description");
        if constexpr (descriptions.size() == 1) {
            constexpr auto value = [:std::meta::constant_of(descriptions[0]):];
            output << ",\"description\":";
            quoted(output, value.text);
        }
        constexpr auto minimums = std::define_static_array(
            std::meta::annotations_of_with_type(field, ^^rig::minimum));
        static_assert(minimums.size() <= 1, "RIG fields need at most one minimum");
        if constexpr (minimums.size() == 1) {
            static_assert(std::meta::is_same_type(std::meta::type_of(field), ^^int) ||
                          std::meta::is_same_type(std::meta::type_of(field), ^^std::optional<int>),
                          "RIG_MINIMUM requires an int or std::optional<int> field");
            constexpr auto value = [:std::meta::constant_of(minimums[0]):];
            output << ",\"minimum\":" << value.value;
        }
        constexpr auto string_choices = std::define_static_array(
            std::meta::annotations_of_with_type(field, ^^rig::string_values));
        static_assert(string_choices.size() <= 1, "RIG fields need at most one string enum");
        if constexpr (string_choices.size() == 1) {
            constexpr auto value = [:std::meta::constant_of(string_choices[0]):];
            output << ",\"string_values\":[";
            for (int index = 0; index < value.count; ++index) {
                if (index) output << ',';
                quoted(output, value.values[index]);
            }
            output << ']';
        }
        emit_value_constraints<field>(output);
        constexpr auto write_only = std::define_static_array(
            std::meta::annotations_of_with_type(field, ^^rig::write_only));
        static_assert(write_only.size() <= 1, "RIG fields need at most one write-only annotation");
        if constexpr (write_only.size() == 1) output << ",\"write_only\":true";
        constexpr auto omit_empty = std::define_static_array(
            std::meta::annotations_of_with_type(field, ^^rig::omit_empty));
        constexpr auto nullable = std::define_static_array(
            std::meta::annotations_of_with_type(field, ^^rig::nullable));
        static_assert(omit_empty.size() <= 1 && nullable.size() <= 1,
                      "RIG optional field annotations may appear once");
        if constexpr (omit_empty.size() == 1 || nullable.size() == 1) {
            static_assert(std::meta::has_template_arguments(std::meta::type_of(field)) &&
                          std::meta::template_of(std::meta::type_of(field)) == ^^std::optional,
                          "RIG omittable and nullable fields require std::optional");
            if constexpr (omit_empty.size() == 1) output << ",\"omit_empty\":true";
            if constexpr (nullable.size() == 1) output << ",\"nullable\":true";
            if constexpr (omit_empty.size() == 1 && nullable.size() == 1) {
                constexpr auto inner = std::meta::template_arguments_of(std::meta::type_of(field))[0];
                static_assert(std::meta::has_template_arguments(inner) &&
                              std::meta::template_of(inner) == ^^std::optional,
                              "omittable nullable fields require nested std::optional");
            }
        }
        output << '}';
    }
    output << "]}";
}

template <std::meta::info Type>
void emit_enum(std::ostream& output) {
    output << "{\"kind\":\"enum\",\"name\":";
    quoted(output, std::meta::identifier_of(Type));
    output << ",\"cpp_name\":";
    quoted(output, qualified_name<Type>());
    output << ",\"values\":[";
    bool first = true;
    template for (constexpr auto value : std::define_static_array(
        std::meta::enumerators_of(Type))) {
        if (!first) output << ',';
        first = false;
        quoted(output, std::meta::identifier_of(value));
    }
    output << "]}";
}

template <std::meta::info Annotation>
consteval std::meta::info service_response_body() {
    constexpr auto response = [:std::meta::constant_of(Annotation):];
    return response.body;
}

template <std::meta::info Annotation>
consteval std::array<char, 256> service_response_description() {
    constexpr auto response = [:std::meta::constant_of(Annotation):];
    std::array<char, 256> text{};
    for (std::size_t index = 0; index < text.size(); ++index) {
        text[index] = response.description[index];
    }
    return text;
}

// Emits a service-wide response such as validation_error or unauthorized.
template <std::meta::info Annotation>
void emit_service_response(std::ostream& output, std::string_view key) {
    output << ",\"" << key << "\":{\"type\":";
    emit_type<service_response_body<Annotation>()>(output);
    output << ",\"description\":";
    quoted(output, service_response_description<Annotation>().data());
    output << '}';
}

template <std::meta::info Type>
void emit_service(std::ostream& output) {
    constexpr auto apis = std::define_static_array(
        std::meta::annotations_of_with_type(Type, ^^rig::api));
    static_assert(apis.size() == 1, "RIG service declarations need exactly one API annotation");
    constexpr auto metadata = [:std::meta::constant_of(apis[0]):];
    output << "{\"title\":";
    quoted(output, metadata.title);
    output << ",\"version\":";
    quoted(output, metadata.version);
    output << ",\"servers\":[";
    bool first = true;
    template for (constexpr auto annotation : std::define_static_array(
        std::meta::annotations_of_with_type(Type, ^^rig::server))) {
        if (!first) output << ',';
        first = false;
        constexpr auto value = [:std::meta::constant_of(annotation):];
        quoted(output, value.url);
    }
    output << ']';
    constexpr auto auth = std::define_static_array(
        std::meta::annotations_of_with_type(Type, ^^rig::bearer_auth));
    static_assert(auth.size() <= 1, "RIG service declarations need at most one bearer auth");
    if constexpr (auth.size() == 1) {
        constexpr auto value = [:std::meta::constant_of(auth[0]):];
        output << ",\"bearer_auth\":{\"name\":";
        quoted(output, value.name);
        output << ",\"format\":";
        quoted(output, value.format);
        output << '}';
    }
    constexpr auto validation = std::define_static_array(
        std::meta::annotations_of_with_type(Type, ^^rig::validation_error));
    static_assert(validation.size() <= 1,
                  "RIG service declarations need at most one validation error");
    if constexpr (validation.size() == 1) {
        emit_service_response<validation[0]>(output, "validation_error");
    }
    constexpr auto unauthorized = std::define_static_array(
        std::meta::annotations_of_with_type(Type, ^^rig::unauthorized));
    static_assert(unauthorized.size() <= 1,
                  "RIG service declarations need at most one unauthorized response");
    if constexpr (unauthorized.size() == 1) {
        emit_service_response<unauthorized[0]>(output, "unauthorized");
    }
    constexpr auto internal = std::define_static_array(
        std::meta::annotations_of_with_type(Type, ^^rig::internal_error));
    static_assert(internal.size() <= 1,
                  "RIG service declarations need at most one internal error");
    if constexpr (internal.size() == 1) {
        emit_service_response<internal[0]>(output, "internal_error");
    }
    constexpr auto method_not_allowed = std::define_static_array(
        std::meta::annotations_of_with_type(Type, ^^rig::method_not_allowed));
    static_assert(method_not_allowed.size() <= 1,
                  "RIG service declarations need at most one method-not-allowed response");
    if constexpr (method_not_allowed.size() == 1) {
        emit_service_response<method_not_allowed[0]>(output, "method_not_allowed");
    }
    output << '}';
}

consteval std::vector<std::meta::info> result_errors(std::meta::info type) {
    auto arguments = std::meta::template_arguments_of(type);
    arguments.erase(arguments.begin());
    return arguments;
}

template <std::meta::info Error>
void emit_result_error(std::ostream& output) {
    constexpr auto arguments = std::define_static_array(std::meta::template_arguments_of(Error));
    constexpr int status = [:arguments[0]:];
    output << "{\"status\":" << status << ",\"type\":";
    emit_type<arguments[1]>(output);
    output << '}';
}

template <std::meta::info Annotation>
consteval int annotated_error_status() {
    constexpr auto response = [:std::meta::constant_of(Annotation):];
    return response.status;
}

template <std::meta::info Annotation>
consteval std::meta::info annotated_error_body() {
    constexpr auto response = [:std::meta::constant_of(Annotation):];
    return response.body;
}

template <std::meta::info Annotation>
consteval std::array<char, 256> annotated_error_description() {
    constexpr auto response = [:std::meta::constant_of(Annotation):];
    std::array<char, 256> text{};
    for (std::size_t index = 0; index < text.size(); ++index) {
        text[index] = response.description[index];
    }
    return text;
}

template <std::meta::info Annotation>
consteval std::vector<std::meta::info> annotated_error_exceptions() {
    constexpr auto response = [:std::meta::constant_of(Annotation):];
    return {response.exceptions, response.exceptions + response.exception_count};
}

// Generated dispatch catches mapped exceptions in annotation order, so an
// earlier type must not also catch a later one.
consteval bool exceptions_in_catch_order(std::meta::info function) {
    std::vector<std::meta::info> seen;
    for (auto annotation : std::meta::annotations_of_with_type(function, ^^rig::error_response)) {
        const auto response = std::meta::extract<rig::error_response>(
            std::meta::constant_of(annotation));
        for (int index = 0; index < response.exception_count; ++index) {
            const auto type = response.exceptions[index];
            if (!std::meta::is_class_type(type)) return false;
            for (auto earlier : seen) {
                if (std::meta::is_same_type(earlier, type) ||
                    std::meta::is_base_of_type(earlier, type)) return false;
            }
            seen.push_back(type);
        }
    }
    return true;
}

template <std::meta::info Annotation>
consteval std::meta::info sse_event_body() {
    constexpr auto event = [:std::meta::constant_of(Annotation):];
    return event.body;
}

template <std::meta::info Annotation>
consteval std::array<char, 64> sse_event_name() {
    constexpr auto event = [:std::meta::constant_of(Annotation):];
    std::array<char, 64> text{};
    for (std::size_t index = 0; index < text.size(); ++index) text[index] = event.name[index];
    return text;
}

template <std::meta::info Function>
void emit_operation(std::ostream& output) {
    static_assert(exceptions_in_catch_order(Function),
                  "RIG mapped exceptions must be distinct classes, listed derived before base");
    constexpr auto annotations = std::define_static_array(
        std::meta::annotations_of_with_type(Function, ^^rig::route));
    static_assert(annotations.size() == 1, "RIG operations need exactly one route");
    constexpr auto route = [:std::meta::constant_of(annotations[0]):];
    output << "{\"name\":";
    quoted(output, std::meta::identifier_of(Function));
    output << ",\"cpp_name\":";
    quoted(output, qualified_name<Function>());
    output << ",\"method\":";
    quoted(output, route.method);
    output << ",\"path\":";
    quoted(output, route.path);
    constexpr auto summaries = std::define_static_array(
        std::meta::annotations_of_with_type(Function, ^^rig::summary));
    static_assert(summaries.size() <= 1, "RIG operations need at most one summary");
    if constexpr (summaries.size() == 1) {
        constexpr auto value = [:std::meta::constant_of(summaries[0]):];
        output << ",\"summary\":";
        quoted(output, value.text);
    }
    constexpr auto descriptions = std::define_static_array(
        std::meta::annotations_of_with_type(Function, ^^rig::description));
    static_assert(descriptions.size() <= 1, "RIG operations need at most one description");
    if constexpr (descriptions.size() == 1) {
        constexpr auto value = [:std::meta::constant_of(descriptions[0]):];
        output << ",\"description\":";
        quoted(output, value.text);
    }
    constexpr auto response_descriptions = std::define_static_array(
        std::meta::annotations_of_with_type(Function, ^^rig::response_description));
    static_assert(response_descriptions.size() <= 1,
                  "RIG operations need at most one success response description");
    if constexpr (response_descriptions.size() == 1) {
        constexpr auto value = [:std::meta::constant_of(response_descriptions[0]):];
        output << ",\"response_description\":";
        quoted(output, value.text);
    }
    constexpr auto public_operations = std::define_static_array(
        std::meta::annotations_of_with_type(Function, ^^rig::public_operation));
    static_assert(public_operations.size() <= 1, "RIG operations need at most one RIG_PUBLIC");
    if constexpr (public_operations.size() == 1) output << ",\"public\":true";
    constexpr auto host_responses = std::define_static_array(
        std::meta::annotations_of_with_type(Function, ^^rig::host_response));
    static_assert(host_responses.size() <= 1, "RIG operations need at most one RIG_HOST_RESPONSE");
    if constexpr (host_responses.size() == 1) {
        constexpr auto value = [:std::meta::constant_of(host_responses[0]):];
        output << ",\"host_response\":";
        quoted(output, value.media_type);
    }
    static_assert(annotation_count<Function, rig::operation_id>() <= 1,
                  "RIG operations need at most one operation ID");
    if constexpr (annotation_count<Function, rig::operation_id>() == 1) {
        constexpr auto value = [:std::meta::constant_of(
            std::meta::annotations_of_with_type(Function, ^^rig::operation_id)[0]):];
        output << ",\"operation_id\":";
        quoted(output, value.text);
    }
    static_assert(annotation_count<Function, rig::string_values>() <= 1 &&
                  annotation_count<Function, rig::format>() <= 1,
                  "RIG operations need at most one response enum and format");
    if constexpr (annotation_count<Function, rig::string_values>() == 1) {
        constexpr auto values = [:std::meta::constant_of(
            std::meta::annotations_of_with_type(Function, ^^rig::string_values)[0]):];
        output << ",\"response_values\":[";
        for (int index = 0; index < values.count; ++index) {
            if (index) output << ',';
            quoted(output, values.values[index]);
        }
        output << ']';
    }
    if constexpr (annotation_count<Function, rig::format>() == 1) {
        constexpr auto value = [:std::meta::constant_of(
            std::meta::annotations_of_with_type(Function, ^^rig::format)[0]):];
        output << ",\"response_format\":";
        quoted(output, value.text);
    }
    if constexpr (annotation_count<Function, rig::sse_event>() > 0) {
        output << ",\"sse_events\":[";
        bool first_event = true;
        template for (constexpr auto annotation : std::define_static_array(
            std::meta::annotations_of_with_type(Function, ^^rig::sse_event))) {
            if (!first_event) output << ',';
            first_event = false;
            output << "{\"name\":";
            quoted(output, sse_event_name<annotation>().data());
            output << ",\"type\":";
            emit_type<sse_event_body<annotation>()>(output);
            output << '}';
        }
        output << ']';
    }
    if constexpr (annotation_count<Function, rig::response_header>() > 0) {
        output << ",\"response_headers\":[";
        bool first_header = true;
        template for (constexpr auto annotation : std::define_static_array(
            std::meta::annotations_of_with_type(Function, ^^rig::response_header))) {
            constexpr auto value = [:std::meta::constant_of(annotation):];
            if (!first_header) output << ',';
            first_header = false;
            output << "{\"name\":";
            quoted(output, value.name);
            output << ",\"description\":";
            quoted(output, value.description);
            output << '}';
        }
        output << ']';
    }
    if constexpr (annotation_count<Function, rig::success_response>() > 0) {
        output << ",\"success_responses\":[";
        bool first_success = true;
        template for (constexpr auto annotation : std::define_static_array(
            std::meta::annotations_of_with_type(Function, ^^rig::success_response))) {
            constexpr auto value = [:std::meta::constant_of(annotation):];
            if (!first_success) output << ',';
            first_success = false;
            output << "{\"status\":" << value.status << ",\"description\":";
            quoted(output, value.description);
            output << '}';
        }
        output << ']';
    }
    constexpr auto success_statuses = std::define_static_array(
        std::meta::annotations_of_with_type(Function, ^^rig::success_status));
    static_assert(success_statuses.size() <= 1, "RIG operations need at most one success status");
    if constexpr (success_statuses.size() == 1) {
        constexpr auto value = [:std::meta::constant_of(success_statuses[0]):];
        output << ",\"success_status\":" << value.status;
    }
    output << ",\"parameters\":[";
    bool first = true;
    template for (constexpr auto parameter : std::define_static_array(
        std::meta::parameters_of(Function))) {
        constexpr auto contexts = std::define_static_array(
            std::meta::annotations_of_with_type(parameter, ^^rig::context));
        static_assert(contexts.size() <= 1, "RIG parameters need at most one context annotation");
        constexpr auto queries = std::define_static_array(
            std::meta::annotations_of_with_type(parameter, ^^rig::query));
        static_assert(contexts.size() == 0 || queries.size() == 0,
                      "RIG context parameters cannot also be query parameters");
        if constexpr (contexts.size() == 0) {
            if (!first) output << ',';
            first = false;
            output << "{\"name\":";
            quoted(output, std::meta::identifier_of(parameter));
            output << ",\"type\":";
            emit_type<std::meta::type_of(parameter)>(output);
            static_assert(queries.size() <= 1, "RIG parameters need at most one query annotation");
            if constexpr (queries.size() == 1) output << ",\"in\":\"query\"";
            static_assert(annotation_count<parameter, rig::header>() <= 1 &&
                          (annotation_count<parameter, rig::header>() == 0 || queries.size() == 0),
                          "RIG parameters are at most one of a query or header parameter");
            if constexpr (annotation_count<parameter, rig::header>() == 1) {
                constexpr auto value = [:std::meta::constant_of(
                    std::meta::annotations_of_with_type(parameter, ^^rig::header)[0]):];
                output << ",\"in\":\"header\",\"header\":";
                quoted(output, value.name);
            }
            constexpr auto ranges = std::define_static_array(
                std::meta::annotations_of_with_type(parameter, ^^rig::range));
            static_assert(ranges.size() <= 1, "RIG parameters need at most one range annotation");
            if constexpr (ranges.size() == 1) {
                constexpr auto bounds = [:std::meta::constant_of(ranges[0]):];
                output << ",\"range\":{\"minimum\":" << bounds.minimum
                       << ",\"maximum\":" << bounds.maximum << '}';
            }
            constexpr auto choices = std::define_static_array(
                std::meta::annotations_of_with_type(parameter, ^^rig::int_values));
            static_assert(choices.size() <= 1, "RIG parameters need at most one integer enum");
            static_assert(ranges.size() == 0 || choices.size() == 0,
                          "RIG parameters cannot have both a range and integer enum");
            if constexpr (choices.size() == 1) {
                constexpr auto values = [:std::meta::constant_of(choices[0]):];
                output << ",\"int_values\":[";
                for (int index = 0; index < values.count; ++index) {
                    if (index) output << ',';
                    output << values.values[index];
                }
                output << ']';
            }
            constexpr auto string_choices = std::define_static_array(
                std::meta::annotations_of_with_type(parameter, ^^rig::string_values));
            static_assert(string_choices.size() <= 1, "RIG parameters need at most one string enum");
            if constexpr (string_choices.size() == 1) {
                constexpr auto values = [:std::meta::constant_of(string_choices[0]):];
                output << ",\"string_values\":[";
                for (int index = 0; index < values.count; ++index) {
                    if (index) output << ',';
                    quoted(output, values.values[index]);
                }
                output << ']';
            }
            constexpr auto minimums = std::define_static_array(
                std::meta::annotations_of_with_type(parameter, ^^rig::minimum));
            static_assert(minimums.size() <= 1, "RIG parameters need at most one minimum");
            if constexpr (minimums.size() == 1) {
                constexpr auto value = [:std::meta::constant_of(minimums[0]):];
                output << ",\"minimum\":" << value.value;
            }
            emit_value_constraints<parameter>(output);
            constexpr auto parameter_descriptions = std::define_static_array(
                std::meta::annotations_of_with_type(parameter, ^^rig::parameter_description));
            static_assert(parameter_descriptions.size() <= 1,
                          "RIG parameters need at most one description");
            if constexpr (parameter_descriptions.size() == 1) {
                constexpr auto value = [:std::meta::constant_of(parameter_descriptions[0]):];
                output << ",\"description\":";
                quoted(output, value.text);
            }
            output << '}';
        }
    }
    output << "],\"context_parameters\":[";
    first = true;
    int position = 0;
    template for (constexpr auto parameter : std::define_static_array(
        std::meta::parameters_of(Function))) {
        constexpr auto contexts = std::define_static_array(
            std::meta::annotations_of_with_type(parameter, ^^rig::context));
        if constexpr (contexts.size() == 1) {
            if (!first) output << ',';
            first = false;
            output << "{\"name\":";
            quoted(output, std::meta::identifier_of(parameter));
            output << ",\"position\":" << position << '}';
        }
        ++position;
    }
    output << "],\"returns\":";
    constexpr auto return_type = std::meta::remove_cvref(std::meta::return_type_of(Function));
    if constexpr (is_result_type(return_type) || is_success_type(return_type)) {
        constexpr auto arguments = std::define_static_array(
            std::meta::template_arguments_of(return_type));
        static_assert(!is_success_type(arguments[0]),
                      "RIG operations choose a success status with rig::success, not in a result");
        emit_type<arguments[0]>(output);
    } else if constexpr (is_host_value_type(return_type)) {
        // The host writes the body; the contract describes it by its media type.
        output << "{\"kind\":\"builtin\",\"name\":\"string\"}";
    } else {
        emit_type<return_type>(output);
    }
    output << ",\"result\":" << (is_result_type(return_type) ? "true" : "false");
    if constexpr (is_success_type(return_type)) output << ",\"chosen_status\":true";
    if constexpr (is_host_value_type(return_type)) output << ",\"host_value\":true";
    output << ",\"errors\":[";
    first = true;
    if constexpr (is_result_type(return_type)) {
        template for (constexpr auto error : std::define_static_array(result_errors(return_type))) {
            if (!first) output << ',';
            first = false;
            emit_result_error<error>(output);
        }
    }
    template for (constexpr auto annotation : std::define_static_array(
        std::meta::annotations_of_with_type(Function, ^^rig::error_response))) {
        if (!first) output << ',';
        first = false;
        constexpr auto status = annotated_error_status<annotation>();
        constexpr auto body = annotated_error_body<annotation>();
        constexpr auto description = annotated_error_description<annotation>();
        output << "{\"status\":" << status << ",\"type\":";
        emit_type<body>(output);
        output << ",\"description\":";
        quoted(output, description.data());
        if constexpr (!annotated_error_exceptions<annotation>().empty()) {
            output << ",\"exceptions\":[";
            bool first_exception = true;
            template for (constexpr auto exception : std::define_static_array(
                annotated_error_exceptions<annotation>())) {
                if (!first_exception) output << ',';
                first_exception = false;
                quoted(output, qualified_name<exception>());
            }
            output << ']';
        }
        output << '}';
    }
    output << ']';
    output << '}';
}

} // namespace detail

// Registration is explicit so reflection never exposes unrelated declarations.
class writer {
public:
    explicit writer(std::ostream& output) : output_(output) {
        output_ << "{\"ir_version\":12,\"types\":[";
    }

    template <std::meta::info Type>
    void add_type() {
        if (stage_ != stage::types) throw std::logic_error("types must precede operations");
        if (!first_) output_ << ',';
        first_ = false;
        if constexpr (std::meta::is_enum_type(Type)) {
            detail::emit_enum<Type>(output_);
        } else if constexpr (std::meta::is_class_type(Type)) {
            detail::emit_record<Type>(output_);
        } else {
            static_assert(std::meta::is_enum_type(Type) || std::meta::is_class_type(Type),
                          "RIG supports only registered records and enums");
        }
    }

    template <std::meta::info Scope>
    void add_namespace() {
        add_namespaces<Scope>();
    }

    template <std::meta::info... Scopes>
    void add_namespaces() {
        static_assert(sizeof...(Scopes) > 0 && (std::meta::is_namespace(Scopes) && ...),
                      "RIG expects namespace roots");
        template for (constexpr auto service : std::define_static_array(
            detail::namespace_services(std::vector<std::meta::info>{Scopes...}))) {
            add_service<service>();
        }
        template for (constexpr auto type : std::define_static_array(
            detail::namespace_types(std::vector<std::meta::info>{Scopes...}))) {
            add_type<type>();
        }
        template for (constexpr auto member : std::define_static_array(
            detail::namespace_operations(std::vector<std::meta::info>{Scopes...}))) {
            add_operation<member>();
        }
    }

    template <std::meta::info Function>
    void add_operation() {
        begin_operations();
        if (!first_) output_ << ',';
        first_ = false;
        detail::emit_operation<Function>(output_);
    }

    template <std::meta::info Type>
    void add_service() {
        if (!service_json_.empty()) throw std::logic_error("RIG service already registered");
        std::ostringstream output;
        detail::emit_service<Type>(output);
        service_json_ = output.str();
    }

    void finish() {
        if (stage_ == stage::finished) throw std::logic_error("writer already finished");
        begin_operations();
        output_ << ']';
        if (!service_json_.empty()) output_ << ",\"service\":" << service_json_;
        output_ << "}\n";
        stage_ = stage::finished;
    }

private:
    enum class stage { types, operations, finished };

    void begin_operations() {
        if (stage_ == stage::finished) throw std::logic_error("writer already finished");
        if (stage_ == stage::types) {
            output_ << "],\"operations\":[";
            stage_ = stage::operations;
            first_ = true;
        }
    }

    std::ostream& output_;
    stage stage_ = stage::types;
    bool first_ = true;
    std::string service_json_;
};

} // namespace rig
