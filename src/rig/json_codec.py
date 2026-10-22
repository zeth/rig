"""Generate C++20 nlohmann JSON codecs from RIG's reflected declaration IR."""

import json
import re

from .ir import identifier, validate


def cpp_literal(value):
    """A C++ literal for a bool, integer or string default from the IR."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(value)


def generate(ir, api_header):
    validate(ir)
    if not re.fullmatch(r"[A-Za-z_0-9/.-]+", api_header):
        raise ValueError("invalid API header path")
    entries = ir["types"]
    names = {entry["cpp_name"] for entry in entries}
    records = {entry["cpp_name"]: entry for entry in entries if entry["kind"] == "record"}

    def inherited_fields(entry):
        """Field names from the record's base records, nearest first."""
        result = []
        base = entry.get("base")
        while base is not None:
            result += [field["name"] for field in records[base]["fields"]]
            base = records[base].get("base")
        return result

    def value_checks(field, source):
        """Length and pattern checks on a JSON string about to be decoded."""
        checks = []
        if "min_length" in field or "max_length" in field:
            maximum = field.get("max_length", "std::numeric_limits<std::size_t>::max()")
            checks += [
                f"        const auto length = {source}.get_ref<const std::string&>().size();",
                f'        if (length < {field.get("min_length", 0)} || length > {maximum})',
                f'            throw std::invalid_argument("invalid length: {field["name"]}");',
            ]
        if "pattern" in field:
            checks += [
                f"        static const std::regex pattern({json.dumps(field['pattern'])});",
                f"        if (!std::regex_search({source}.get_ref<const std::string&>(), pattern))",
                f'            throw std::invalid_argument("invalid format: {field["name"]}");',
            ]
        return checks

    def cpp_type(ref):
        kind = ref["kind"]
        if kind == "builtin":
            try:
                return {"int": "int", "int64": "long long", "double": "double",
                        "bool": "bool", "string": "std::string",
                        "object": "nlohmann::json"}[ref["name"]]
            except KeyError:
                raise ValueError(f"unsupported builtin type: {ref['name']}") from None
        if kind == "named":
            name = ref["name"]
            if name not in names:
                raise ValueError(f"unregistered type: {name}")
            return name
        if kind in {"array", "optional"}:
            inner = cpp_type(ref["items"] if kind == "array" else ref["value"])
            container = "vector" if kind == "array" else "optional"
            return f"std::{container}<{inner}>"
        if kind == "map":
            return f"std::map<std::string, {cpp_type(ref['values'])}>"
        if kind == "variant":
            return f"std::variant<{', '.join(cpp_type(item) for item in ref['alternatives'])}>"
        raise ValueError(f"unsupported type kind: {kind}")

    lines = [
        "// Generated from RIG IR; do not edit.",
        "#pragma once",
        f'#include "{api_header}"',
        "#include <nlohmann/json.hpp>",
        "#include <cstdint>",
        "#include <limits>",
        "#include <map>",
        "#include <regex>",
        "#include <optional>",
        "#include <stdexcept>",
        "#include <string>",
        "#include <type_traits>",
        "#include <variant>",
        "#include <vector>",
        "",
        "namespace rig_json {",
        "using json = nlohmann::json;",
        "template <typename T> struct codec;",
        "",
        "template <> struct codec<int> {",
        "    static json encode(int value) { return value; }",
        "    static int decode(const json& value) {",
        '        if (!value.is_number_integer()) throw std::invalid_argument("expected int");',
        "        if (value.is_number_unsigned()) {",
        "            if (value.get<std::uint64_t>() > static_cast<std::uint64_t>(std::numeric_limits<int>::max()))",
        '                throw std::invalid_argument("int out of range");',
        "        } else {",
        "            const auto number = value.get<std::int64_t>();",
        "            if (number < std::numeric_limits<int>::min() || number > std::numeric_limits<int>::max())",
        '                throw std::invalid_argument("int out of range");',
        "        }",
        "        return value.get<int>();",
        "    }",
        "};",
        "template <> struct codec<bool> {",
        "    static json encode(bool value) { return value; }",
        "    static bool decode(const json& value) {",
        '        if (!value.is_boolean()) throw std::invalid_argument("expected bool");',
        "        return value.get<bool>();",
        "    }",
        "};",
        "template <> struct codec<long long> {",
        "    static json encode(long long value) { return value; }",
        "    static long long decode(const json& value) {",
        '        if (!value.is_number_integer()) throw std::invalid_argument("expected int64");',
        "        if (value.is_number_unsigned() &&",
        "            value.get<std::uint64_t>() > static_cast<std::uint64_t>(std::numeric_limits<long long>::max()))",
        '            throw std::invalid_argument("int64 out of range");',
        "        return value.get<long long>();",
        "    }",
        "};",
        "template <> struct codec<double> {",
        "    static json encode(double value) { return value; }",
        "    static double decode(const json& value) {",
        '        if (!value.is_number()) throw std::invalid_argument("expected double");',
        "        return value.get<double>();",
        "    }",
        "};",
        "template <> struct codec<std::string> {",
        "    static json encode(const std::string& value) { return value; }",
        "    static std::string decode(const json& value) {",
        '        if (!value.is_string()) throw std::invalid_argument("expected string");',
        "        return value.get<std::string>();",
        "    }",
        "};",
        "// A free-form JSON object: any members, but an object.",
        "template <> struct codec<json> {",
        "    static json encode(const json& value) {",
        '        if (!value.is_object()) throw std::invalid_argument("expected object");',
        "        return value;",
        "    }",
        "    static json decode(const json& value) { return encode(value); }",
        "};",
        "template <typename T> struct codec<std::map<std::string, T>> {",
        "    static json encode(const std::map<std::string, T>& value) {",
        "        json result = json::object();",
        "        for (const auto& [key, item] : value) result[key] = codec<T>::encode(item);",
        "        return result;",
        "    }",
        "    static std::map<std::string, T> decode(const json& value) {",
        '        if (!value.is_object()) throw std::invalid_argument("expected object");',
        "        std::map<std::string, T> result;",
        "        for (auto it = value.begin(); it != value.end(); ++it)",
        "            result.emplace(it.key(), codec<T>::decode(it.value()));",
        "        return result;",
        "    }",
        "};",
        "// OpenAPI oneOf: exactly one alternative must accept the value.",
        "template <typename... Ts> struct codec<std::variant<Ts...>> {",
        "    static json encode(const std::variant<Ts...>& value) {",
        "        return std::visit([](const auto& item) {",
        "            return codec<std::decay_t<decltype(item)>>::encode(item);",
        "        }, value);",
        "    }",
        "    static std::variant<Ts...> decode(const json& value) {",
        "        std::optional<std::variant<Ts...>> result;",
        "        int matches = 0;",
        "        (try_alternative<Ts>(value, result, matches), ...);",
        "        if (matches == 0) throw std::invalid_argument(\"no alternative matches\");",
        "        if (matches > 1) throw std::invalid_argument(\"several alternatives match\");",
        "        return std::move(*result);",
        "    }",
        "    template <typename T>",
        "    static void try_alternative(const json& value, std::optional<std::variant<Ts...>>& result,",
        "                                int& matches) {",
        "        try {",
        "            T decoded = codec<T>::decode(value);",
        "            if (!result) result.emplace(std::in_place_type<T>, std::move(decoded));",
        "            ++matches;",
        "        } catch (const std::invalid_argument&) {",
        "        } catch (const json::exception&) {",
        "        }",
        "    }",
        "};",
        "template <typename T> struct codec<std::vector<T>> {",
        "    static json encode(const std::vector<T>& value) {",
        "        json result = json::array();",
        "        for (const auto& item : value) result.push_back(codec<T>::encode(item));",
        "        return result;",
        "    }",
        "    static std::vector<T> decode(const json& value) {",
        '        if (!value.is_array()) throw std::invalid_argument("expected array");',
        "        std::vector<T> result;",
        "        for (const auto& item : value) result.push_back(codec<T>::decode(item));",
        "        return result;",
        "    }",
        "};",
        "template <typename T> struct codec<std::optional<T>> {",
        "    static json encode(const std::optional<T>& value) {",
        "        return value ? codec<T>::encode(*value) : json(nullptr);",
        "    }",
        "    static std::optional<T> decode(const json& value) {",
        "        return value.is_null() ? std::nullopt : std::optional<T>(codec<T>::decode(value));",
        "    }",
        "};",
        "",
    ]

    for entry in entries:
        qualified = entry["cpp_name"]
        lines += [
            f"template <> struct codec<{qualified}> {{",
            f"    static json encode(const {qualified}& value);",
            f"    static {qualified} decode(const json& value);",
            "};",
        ]
    lines.append("")

    for entry in entries:
        name = identifier(entry["name"])
        qualified = entry["cpp_name"]
        lines.append(f"inline json codec<{qualified}>::encode(const {qualified}& value) {{")
        if entry["kind"] == "enum":
            values = [identifier(value) for value in entry["values"]]
            lines.append("    switch (value) {")
            for value in values:
                lines.append(f'    case {qualified}::{value}: return "{value}";')
            lines += ["    }", f'    throw std::invalid_argument("invalid {name}");']
        elif entry.get("value"):
            field = entry["fields"][0]
            lines.append(f"    return codec<{cpp_type(field['type'])}>::encode(value.{field['name']});")
        else:
            fields = entry["fields"]
            if "base" in entry:
                lines.append(f"    json result = codec<{entry['base']}>::encode(value);")
            else:
                lines.append("    json result = json::object();")
            for field in fields:
                field_name = field["name"]
                if "bool_value" in field:
                    lines.append(
                        f'    if (value.{field_name} != {str(field["bool_value"]).lower()}) '
                        f'throw std::invalid_argument("invalid {field_name}");'
                    )
                if "string_values" in field:
                    # Each of omit_empty and nullable wraps the string in one optional.
                    layers = int(bool(field.get("omit_empty"))) + int(bool(field.get("nullable")))
                    value = "*" * layers + f"value.{field_name}"
                    invalid = " && ".join(
                        f'{value} != {json.dumps(choice)}' for choice in field["string_values"]
                    )
                    present = "".join(f'{"*" * depth}value.{field_name} && ' for depth in range(layers))
                    lines.append(
                        f'    if ({present}{invalid}) '
                        f'throw std::invalid_argument("invalid {field_name}");'
                    )
                assignment = (
                    f'    result["{field_name}"] = '
                    f'codec<{cpp_type(field["type"])}>::encode(value.{field_name});'
                )
                if field.get("omit_empty"):
                    lines.append(f"    if (value.{field_name}) {{")
                    lines.append("    " + assignment)
                    lines.append("    }")
                else:
                    lines.append(assignment)
            lines.append("    return result;")
        lines += ["}", f"inline {qualified} codec<{qualified}>::decode(const json& value) {{"]
        if entry["kind"] == "enum":
            lines.append(f'    if (!value.is_string()) throw std::invalid_argument("expected {name}");')
            for value in values:
                lines.append(f'    if (value == "{value}") return {qualified}::{value};')
            lines.append(f'    throw std::invalid_argument("unknown {name}");')
        elif entry.get("value"):
            field = entry["fields"][0]
            checks = value_checks(field, "value")
            if "string_values" in field:
                invalid = " && ".join(f"value != {json.dumps(choice)}" for choice in field["string_values"])
                checks.append(f'        if ({invalid}) throw std::invalid_argument("invalid {field["name"]}");')
            if checks:
                lines += ["    if (value.is_string()) {", *checks, "    }"]
            lines.append(f"    return {qualified}{{codec<{cpp_type(field['type'])}>::decode(value)}};")
        else:
            lines.append(f'    if (!value.is_object()) throw std::invalid_argument("expected {name}");')
            if "min_properties" in entry:
                lines.append(f'    if (value.size() < {entry["min_properties"]}) '
                             f'throw std::invalid_argument("too few {name} fields");')
            for field in fields:
                if not field.get("omit_empty") and "default" not in field:
                    lines.append(
                        f'    if (!value.contains("{field["name"]}")) '
                        f'throw std::invalid_argument("missing {field["name"]}");'
                    )
            if not entry.get("open", False):
                allowed = " && ".join(
                    f'it.key() != "{field_name}"'
                    for field_name in [field["name"] for field in fields] + inherited_fields(entry)
                ) or "true"
                lines.append("    for (auto it = value.begin(); it != value.end(); ++it)")
                lines.append(f'        if ({allowed}) throw std::invalid_argument("unexpected {name} field");')
            for field in fields:
                if "bool_value" in field:
                    lines.append(
                        f'    if (value.at("{field["name"]}") != {str(field["bool_value"]).lower()}) '
                        f'throw std::invalid_argument("invalid {field["name"]}");'
                    )
                if "string_values" in field:
                    field_name = field["name"]
                    invalid = " && ".join(
                        f'value.at("{field_name}") != {json.dumps(choice)}'
                        for choice in field["string_values"]
                    )
                    present = (f'value.contains("{field_name}") && ' if field.get("omit_empty") else '') + (
                        f'!value.at("{field_name}").is_null() && '
                        if field.get("omit_empty") or field.get("nullable") else '')
                    lines.append(
                        f'    if ({present}{invalid}) '
                        f'throw std::invalid_argument("invalid {field_name}");'
                    )
            for field in fields:
                checks = value_checks(field, f'value.at("{field["name"]}")')
                if checks:
                    field_name = field["name"]
                    lines += [
                        f'    if (value.contains("{field_name}") && value.at("{field_name}").is_string()) {{',
                        *checks,
                        "    }",
                    ]
            if "base" in entry:
                # The base decodes the members this record does not add.
                lines.append("    json base = value;")
                lines += [f'    base.erase("{field["name"]}");' for field in fields]
            lines.append(f"    return {qualified}{{")
            if "base" in entry:
                lines.append(f"        codec<{entry['base']}>::decode(base),")
            for field in fields:
                decoded = f'codec<{cpp_type(field["type"])}>::decode(value.at("{field["name"]}"))'
                if field.get("omit_empty") and field.get("nullable"):
                    inner_type = cpp_type(field["type"]["value"])
                    decoded = (f'std::optional<{inner_type}>{{std::in_place, '
                               f'codec<{inner_type}>::decode(value.at("{field["name"]}"))}}')
                if field.get("omit_empty"):
                    decoded = f'value.contains("{field["name"]}") ? {decoded} : std::nullopt'
                if "default" in field:
                    fallback = f'{cpp_type(field["type"])}({cpp_literal(field["default"])})'
                    decoded = f'value.contains("{field["name"]}") ? {decoded} : {fallback}'
                lines.append(f'        {decoded},')
            lines.append("    };")
        lines += ["}", ""]

    lines += [
        "template <typename T> json encode(const T& value) { return codec<T>::encode(value); }",
        "template <typename T> T decode(const json& value) { return codec<T>::decode(value); }",
        "} // namespace rig_json",
    ]
    lines += event_constructors(ir, cpp_type)
    return "\n".join(lines) + "\n"


CPP_KEYWORDS = frozenset("""
    alignas alignof and and_eq asm auto bitand bitor bool break case catch char class compl
    concept const consteval constexpr constinit const_cast continue co_await co_return co_yield
    decltype default delete do double dynamic_cast else enum explicit export extern false float
    for friend goto if inline int long mutable namespace new noexcept not not_eq nullptr operator
    or or_eq private protected public register reinterpret_cast requires return short signed
    sizeof static static_assert static_cast struct switch template this thread_local throw true
    try typedef typeid typename union unsigned using virtual void volatile wchar_t while xor xor_eq
""".split())


def event_function(name):
    """The C++ name for an event's constructor: card.changed becomes card_changed."""
    function = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if function[0].isdigit():
        function = "_" + function
    return function + "_" if function in CPP_KEYWORDS else function


def event_constructors(ir, cpp_type):
    """rig_events::<name>(data) for every declared event, overloaded by its data type."""
    events = {}
    for operation in ir["operations"]:
        for event in operation.get("sse_events", []):
            key = (event_function(event["name"]), cpp_type(event["type"]))
            if events.setdefault(key, event["name"]) != event["name"]:
                raise ValueError(f"events {events[key]!r} and {event['name']!r} need different "
                                 f"constructors but both are {key[0]}({key[1]})")
    if not events:
        return []
    lines = [
        "",
        "// An event can only be built with the data type its operation declares for it.",
        "namespace rig_events {",
    ]
    for (function, data_type), name in sorted(events.items()):
        lines += [
            f"inline rig::event<nlohmann::json> {function}(const {data_type}& data) {{",
            f"    return {{{json.dumps(name)}, rig_json::encode(data)}};",
            "}",
        ]
    lines.append("} // namespace rig_events")
    return lines
