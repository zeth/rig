"""Generate C++20 HTTP dispatch from RIG's reflected operation IR."""

import json
import re

from .ir import identifier, route_pattern, route_priority, validate


def generate(ir, codec_header):
    validate(ir)
    if not re.fullmatch(r"[A-Za-z_0-9/.-]+", codec_header):
        raise ValueError("invalid codec header path")

    names = {entry["cpp_name"] for entry in ir["types"]}

    def cpp_type(ref):
        if ref["kind"] == "builtin":
            return {"int": "int", "bool": "bool", "string": "std::string"}[ref["name"]]
        if ref["kind"] == "named":
            name = ref["name"]
            if name not in names:
                raise ValueError(f"unregistered type: {name}")
            return name
        if ref["kind"] in {"array", "optional"}:
            inner = cpp_type(ref["items"] if ref["kind"] == "array" else ref["value"])
            container = "vector" if ref["kind"] == "array" else "optional"
            return f"std::{container}<{inner}>"
        raise ValueError(f"unsupported operation parameter type: {ref['kind']}")

    lines = [
        "// Generated from RIG IR; do not edit.",
        "#pragma once",
        f'#include "{codec_header}"',
        "#include <optional>",
        "#include <regex>",
        "#include <stdexcept>",
        "#include <string>",
        "#include <type_traits>",
        "#include <variant>",
        "",
        "namespace rig_http {",
        "using json = nlohmann::json;",
        "struct response { int status; json body; };",
        "template <typename T> T decode_body(const std::string& body) {",
        "    try {",
        "        return rig_json::decode<T>(json::parse(body));",
        "    } catch (const json::exception& error) {",
        "        throw std::invalid_argument(error.what());",
        "    }",
        "}",
        "inline std::optional<response> dispatch(const std::string& method,",
        "                                    const std::string& path,",
        "                                    const std::string& body) {",
        "    std::smatch match;",
    ]

    # Validated overlapping routes have a strict specificity order. Keep IR
    # order for routes with the same priority or disjoint match sets.
    ordered = sorted(enumerate(ir["operations"]), key=lambda pair: route_priority(pair[1]))
    for index, operation in ordered:
        name = identifier(operation["name"])
        parameters = {identifier(item["name"]): item for item in operation["parameters"]}
        pattern, captures = route_pattern(operation["path"], parameters)
        bodies = [item for item in operation["parameters"] if item["name"] not in captures]
        if len(bodies) > 1:
            raise ValueError(f"multiple body parameters in {name}")
        lines += [
            f"    static const std::regex route_{index}({json.dumps(pattern)});",
            f'    if (method == "{operation["method"]}" && std::regex_match(path, match, route_{index})) {{',
        ]
        arguments = []
        for parameter in operation["parameters"]:
            param_name = identifier(parameter["name"])
            param_type = cpp_type(parameter["type"])
            if param_name in captures:
                value = f"match[{captures[param_name]}].str()"
                value = f"std::stoi({value})" if param_type == "int" else value
            else:
                value = f"decode_body<{param_type}>(body)"
            arguments.append(value)
        call = f"{operation['cpp_name']}({', '.join(arguments)})"
        if operation.get("errors"):
            success = cpp_type(operation["returns"])
            lines += [
                f"        const auto outcome = {call};",
                "        return std::visit([](const auto& value) -> response {",
                "            using value_type = std::decay_t<decltype(value)>;",
                f"            if constexpr (std::is_same_v<value_type, {success}>) {{",
                "                return {200, rig_json::encode(value)};",
                "            } else {",
                "                return {value_type::status, rig_json::encode(value.body)};",
                "            }",
                "        }, outcome.value());",
            ]
        else:
            lines.append(f"        return response{{200, rig_json::encode({call})}};")
        lines.append("    }")
    lines += [
        "    return std::nullopt;",
        "}",
        "} // namespace rig_http",
    ]
    return "\n".join(lines) + "\n"
