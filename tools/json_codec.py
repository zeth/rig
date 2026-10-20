#!/usr/bin/env python3
"""Generate C++20 nlohmann JSON codecs from RIG's reflected declaration IR."""

import argparse
import json
import re
import sys


IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z_0-9]*\Z")


def identifier(value):
    if not IDENTIFIER.fullmatch(value):
        raise ValueError(f"invalid C++ identifier: {value}")
    return value


def generate(ir, namespace, api_header):
    if ir.get("ir_version") != 2:
        raise ValueError("unsupported RIG IR version")
    namespace = "::".join(identifier(part) for part in namespace.split("::"))
    if not re.fullmatch(r"[A-Za-z_0-9/.-]+", api_header):
        raise ValueError("invalid API header path")
    entries = ir["types"]
    names = {identifier(entry["name"]) for entry in entries}
    if len(names) != len(entries):
        raise ValueError("duplicate type name")

    def cpp_type(ref):
        kind = ref["kind"]
        if kind == "builtin":
            try:
                return {"int": "int", "bool": "bool", "string": "std::string"}[ref["name"]]
            except KeyError:
                raise ValueError(f"unsupported builtin type: {ref['name']}") from None
        if kind == "named":
            name = identifier(ref["name"])
            if name not in names:
                raise ValueError(f"unregistered type: {name}")
            return f"{namespace}::{name}"
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
        name = identifier(entry["name"])
        if entry["kind"] not in {"enum", "record"}:
            raise ValueError(f"unsupported declaration kind: {entry['kind']}")
        qualified = f"{namespace}::{name}"
        lines += [
            f"template <> struct codec<{qualified}> {{",
            f"    static json encode(const {qualified}& value);",
            f"    static {qualified} decode(const json& value);",
            "};",
        ]
    lines.append("")

    for entry in entries:
        name = identifier(entry["name"])
        qualified = f"{namespace}::{name}"
        lines.append(f"inline json codec<{qualified}>::encode(const {qualified}& value) {{")
        if entry["kind"] == "enum":
            values = [identifier(value) for value in entry["values"]]
            if len(set(values)) != len(values):
                raise ValueError(f"duplicate enum value in {name}")
            lines.append("    switch (value) {")
            for value in values:
                lines.append(f'    case {qualified}::{value}: return "{value}";')
            lines += ["    }", f'    throw std::invalid_argument("invalid {name}");']
        else:
            fields = entry["fields"]
            field_names = [identifier(field["name"]) for field in fields]
            if len(set(field_names)) != len(field_names):
                raise ValueError(f"duplicate field in {name}")
            lines.append("    json result = json::object();")
            for field in fields:
                field_name = field["name"]
                lines.append(
                    f'    result["{field_name}"] = codec<{cpp_type(field["type"])}>::encode(value.{field_name});'
                )
            lines.append("    return result;")
        lines += ["}", f"inline {qualified} codec<{qualified}>::decode(const json& value) {{"]
        if entry["kind"] == "enum":
            lines.append(f'    if (!value.is_string()) throw std::invalid_argument("expected {name}");')
            for value in values:
                lines.append(f'    if (value == "{value}") return {qualified}::{value};')
            lines.append(f'    throw std::invalid_argument("unknown {name}");')
        else:
            lines.append(f'    if (!value.is_object() || value.size() != {len(fields)}')
            for field in fields:
                lines.append(f'        || !value.contains("{field["name"]}")')
            lines.append(f') throw std::invalid_argument("expected {name}");')
            lines.append(f"    return {qualified}{{")
            for field in fields:
                lines.append(
                    f'        codec<{cpp_type(field["type"])}>::decode(value.at("{field["name"]}")),'
                )
            lines.append("    };")
        lines += ["}", ""]

    lines += [
        "template <typename T> json encode(const T& value) { return codec<T>::encode(value); }",
        "template <typename T> T decode(const json& value) { return codec<T>::decode(value); }",
        "} // namespace rig_json",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--api-header", required=True)
    args = parser.parse_args()
    try:
        sys.stdout.write(generate(json.load(sys.stdin), args.namespace, args.api_header))
    except (KeyError, ValueError) as error:
        print(f"RIG JSON codec generation failed: {error}", file=sys.stderr)
        sys.exit(1)
