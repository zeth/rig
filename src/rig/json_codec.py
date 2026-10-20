"""Generate C++20 nlohmann JSON codecs from RIG's reflected declaration IR."""

import re

from .ir import identifier, validate


def generate(ir, api_header):
    validate(ir)
    if not re.fullmatch(r"[A-Za-z_0-9/.-]+", api_header):
        raise ValueError("invalid API header path")
    entries = ir["types"]
    names = {entry["cpp_name"] for entry in entries}

    def cpp_type(ref):
        kind = ref["kind"]
        if kind == "builtin":
            try:
                return {"int": "int", "int64": "long long", "double": "double",
                        "bool": "bool", "string": "std::string"}[ref["name"]]
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
        raise ValueError(f"unsupported type kind: {kind}")

    lines = [
        "// Generated from RIG IR; do not edit.",
        "#pragma once",
        f'#include "{api_header}"',
        "#include <nlohmann/json.hpp>",
        "#include <cstdint>",
        "#include <limits>",
        "#include <optional>",
        "#include <stdexcept>",
        "#include <string>",
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
        else:
            fields = entry["fields"]
            lines.append("    json result = json::object();")
            for field in fields:
                field_name = field["name"]
                if "bool_value" in field:
                    lines.append(
                        f'    if (value.{field_name} != {str(field["bool_value"]).lower()}) '
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
        else:
            lines.append('    if (!value.is_object()')
            for field in fields:
                if not field.get("omit_empty"):
                    lines.append(f'        || !value.contains("{field["name"]}")')
            lines.append(f') throw std::invalid_argument("expected {name}");')
            if not entry.get("open", False):
                allowed = " && ".join(
                    f'it.key() != "{field["name"]}"' for field in fields
                ) or "true"
                lines.append("    for (auto it = value.begin(); it != value.end(); ++it)")
                lines.append(f'        if ({allowed}) throw std::invalid_argument("unexpected {name} field");')
            for field in fields:
                if "bool_value" in field:
                    lines.append(
                        f'    if (value.at("{field["name"]}") != {str(field["bool_value"]).lower()}) '
                        f'throw std::invalid_argument("invalid {field["name"]}");'
                    )
            lines.append(f"    return {qualified}{{")
            for field in fields:
                decoded = f'codec<{cpp_type(field["type"])}>::decode(value.at("{field["name"]}"))'
                if field.get("omit_empty") and field.get("nullable"):
                    inner_type = cpp_type(field["type"]["value"])
                    decoded = (f'std::optional<{inner_type}>{{std::in_place, '
                               f'codec<{inner_type}>::decode(value.at("{field["name"]}"))}}')
                if field.get("omit_empty"):
                    decoded = f'value.contains("{field["name"]}") ? {decoded} : std::nullopt'
                lines.append(f'        {decoded},')
            lines.append("    };")
        lines += ["}", ""]

    lines += [
        "template <typename T> json encode(const T& value) { return codec<T>::encode(value); }",
        "template <typename T> T decode(const json& value) { return codec<T>::decode(value); }",
        "} // namespace rig_json",
    ]
    return "\n".join(lines) + "\n"
