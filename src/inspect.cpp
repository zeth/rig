#include <dodger/api.hpp>

#include <meta>
#include <iostream>
#include <string>
#include <string_view>

namespace {

void quoted(std::string_view value) {
    std::cout << '"';
    for (unsigned char ch : value) {
        switch (ch) {
        case '"': std::cout << "\\\""; break;
        case '\\': std::cout << "\\\\"; break;
        case '\n': std::cout << "\\n"; break;
        case '\r': std::cout << "\\r"; break;
        case '\t': std::cout << "\\t"; break;
        default:
            if (ch < 0x20) {
                constexpr char digits[] = "0123456789abcdef";
                std::cout << "\\u00" << digits[ch >> 4] << digits[ch & 15];
            } else {
                std::cout << ch;
            }
        }
    }
    std::cout << '"';
}

template <std::meta::info Type>
void emit_type() {
    constexpr auto type = std::meta::remove_cvref(Type);
    if constexpr (std::meta::is_same_type(type, ^^int)) {
        std::cout << "{\"kind\":\"builtin\",\"name\":\"int\"}";
    } else if constexpr (std::meta::is_same_type(type, ^^bool)) {
        std::cout << "{\"kind\":\"builtin\",\"name\":\"bool\"}";
    } else if constexpr (std::meta::is_same_type(type, ^^std::string)) {
        std::cout << "{\"kind\":\"builtin\",\"name\":\"string\"}";
    } else if constexpr (std::meta::has_template_arguments(type)) {
        constexpr auto templ = std::meta::template_of(type);
        if constexpr (templ == ^^std::vector || templ == ^^std::optional) {
            constexpr auto arguments = std::define_static_array(
                std::meta::template_arguments_of(type));
            std::cout << "{\"kind\":\"";
            if constexpr (templ == ^^std::vector) {
                std::cout << "array\",\"items\":";
            } else {
                std::cout << "optional\",\"value\":";
            }
            emit_type<arguments[0]>();
            std::cout << '}';
        } else {
            // The converter rejects any unregistered specialization.
            std::cout << "{\"kind\":\"unsupported\",\"name\":";
            quoted(std::meta::display_string_of(type));
            std::cout << '}';
        }
    } else {
        std::cout << "{\"kind\":\"named\",\"name\":";
        quoted(std::meta::identifier_of(type));
        std::cout << '}';
    }
}

template <std::meta::info Type>
void emit_record() {
    std::cout << "{\"kind\":\"record\",\"name\":";
    quoted(std::meta::identifier_of(Type));
    std::cout << ",\"fields\":[";
    bool first = true;
    template for (constexpr auto field : std::define_static_array(
        std::meta::nonstatic_data_members_of(Type, std::meta::access_context::unchecked()))) {
        if (!first) std::cout << ',';
        first = false;
        std::cout << "{\"name\":";
        quoted(std::meta::identifier_of(field));
        std::cout << ",\"type\":";
        emit_type<std::meta::type_of(field)>();
        std::cout << '}';
    }
    std::cout << "]}";
}

template <std::meta::info Type>
void emit_enum() {
    std::cout << "{\"kind\":\"enum\",\"name\":";
    quoted(std::meta::identifier_of(Type));
    std::cout << ",\"values\":[";
    bool first = true;
    template for (constexpr auto value : std::define_static_array(
        std::meta::enumerators_of(Type))) {
        if (!first) std::cout << ',';
        first = false;
        quoted(std::meta::identifier_of(value));
    }
    std::cout << "]}";
}

template <std::meta::info Function>
void emit_operation() {
    constexpr auto annotations = std::define_static_array(
        std::meta::annotations_of_with_type(Function, ^^rig::route));
    static_assert(annotations.size() == 1, "RIG operations need exactly one route");
    constexpr auto route = [:std::meta::constant_of(annotations[0]):];
    std::cout << "{\"name\":";
    quoted(std::meta::identifier_of(Function));
    std::cout << ",\"method\":";
    quoted(route.method);
    std::cout << ",\"path\":";
    quoted(route.path);
    std::cout << ",\"parameters\":[";
    bool first = true;
    template for (constexpr auto parameter : std::define_static_array(
        std::meta::parameters_of(Function))) {
        if (!first) std::cout << ',';
        first = false;
        std::cout << "{\"name\":";
        quoted(std::meta::identifier_of(parameter));
        std::cout << ",\"type\":";
        emit_type<std::meta::type_of(parameter)>();
        std::cout << '}';
    }
    std::cout << "],\"returns\":";
    emit_type<std::meta::return_type_of(Function)>();
    std::cout << '}';
}

} // namespace

int main() {
    // Registration is explicit so reflection never exposes unrelated declarations.
    std::cout << "{\"ir_version\":2,\"types\":[";
    emit_enum<^^dodger::Move>();
    std::cout << ',';
    emit_enum<^^dodger::GameStatus>();
    std::cout << ',';
    emit_enum<^^dodger::Winner>();
    std::cout << ',';
    emit_record<^^dodger::Player>();
    std::cout << ',';
    emit_record<^^dodger::Obstacle>();
    std::cout << ',';
    emit_record<^^dodger::Action>();
    std::cout << ',';
    emit_record<^^dodger::GameState>();
    std::cout << "],\"operations\":[";
    emit_operation<^^dodger::get_game>();
    std::cout << ',';
    emit_operation<^^dodger::submit_action>();
    std::cout << "]}\n";
}
