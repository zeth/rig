#pragma once

#ifndef RIG_GENERATING
#error "rig/inspect.hpp requires C++26 reflection and RIG_GENERATING"
#endif

#include <rig/route.hpp>

#include <meta>
#include <ostream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>
#include <optional>

namespace rig {
namespace detail {

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

template <std::meta::info Type>
void emit_type(std::ostream& output) {
    constexpr auto type = std::meta::remove_cvref(Type);
    if constexpr (std::meta::is_same_type(type, ^^int)) {
        output << "{\"kind\":\"builtin\",\"name\":\"int\"}";
    } else if constexpr (std::meta::is_same_type(type, ^^bool)) {
        output << "{\"kind\":\"builtin\",\"name\":\"bool\"}";
    } else if constexpr (std::meta::is_same_type(type, ^^std::string)) {
        output << "{\"kind\":\"builtin\",\"name\":\"string\"}";
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
        } else {
            // The converter rejects any unregistered specialization.
            output << "{\"kind\":\"unsupported\",\"name\":";
            quoted(output, std::meta::display_string_of(type));
            output << '}';
        }
    } else {
        output << "{\"kind\":\"named\",\"name\":";
        quoted(output, std::meta::identifier_of(type));
        output << '}';
    }
}

template <std::meta::info Type>
void emit_record(std::ostream& output) {
    output << "{\"kind\":\"record\",\"name\":";
    quoted(output, std::meta::identifier_of(Type));
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
        output << '}';
    }
    output << "]}";
}

template <std::meta::info Type>
void emit_enum(std::ostream& output) {
    output << "{\"kind\":\"enum\",\"name\":";
    quoted(output, std::meta::identifier_of(Type));
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

template <std::meta::info Function>
void emit_operation(std::ostream& output) {
    constexpr auto annotations = std::define_static_array(
        std::meta::annotations_of_with_type(Function, ^^rig::route));
    static_assert(annotations.size() == 1, "RIG operations need exactly one route");
    constexpr auto route = [:std::meta::constant_of(annotations[0]):];
    output << "{\"name\":";
    quoted(output, std::meta::identifier_of(Function));
    output << ",\"method\":";
    quoted(output, route.method);
    output << ",\"path\":";
    quoted(output, route.path);
    output << ",\"parameters\":[";
    bool first = true;
    template for (constexpr auto parameter : std::define_static_array(
        std::meta::parameters_of(Function))) {
        if (!first) output << ',';
        first = false;
        output << "{\"name\":";
        quoted(output, std::meta::identifier_of(parameter));
        output << ",\"type\":";
        emit_type<std::meta::type_of(parameter)>(output);
        output << '}';
    }
    output << "],\"returns\":";
    emit_type<std::meta::return_type_of(Function)>(output);
    output << '}';
}

} // namespace detail

// Registration is explicit so reflection never exposes unrelated declarations.
class writer {
public:
    explicit writer(std::ostream& output) : output_(output) {
        output_ << "{\"ir_version\":2,\"types\":[";
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

    template <std::meta::info Function>
    void add_operation() {
        begin_operations();
        if (!first_) output_ << ',';
        first_ = false;
        detail::emit_operation<Function>(output_);
    }

    void finish() {
        if (stage_ == stage::finished) throw std::logic_error("writer already finished");
        begin_operations();
        output_ << "]}\n";
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
};

} // namespace rig
