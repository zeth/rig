"""Generate C++20 HTTP dispatch from RIG's reflected operation IR."""

import json
import re

from .ir import identifier, route_pattern, validate


def generate(ir, namespace, codec_header):
    validate(ir)
    namespace = "::".join(identifier(part) for part in namespace.split("::"))
    if not re.fullmatch(r"[A-Za-z_0-9/.-]+", codec_header):
        raise ValueError("invalid codec header path")

    names = {identifier(entry["name"]) for entry in ir["types"]}

    def cpp_type(ref):
        if ref["kind"] == "builtin":
            return {"int": "int", "bool": "bool", "string": "std::string"}[ref["name"]]
        if ref["kind"] == "named":
            name = identifier(ref["name"])
            if name not in names:
                raise ValueError(f"unregistered type: {name}")
            return f"{namespace}::{name}"
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
        "",
        "namespace rig_http {",
        "using json = nlohmann::json;",
        "template <typename T> T decode_body(const std::string& body) {",
        "    try {",
        "        return rig_json::decode<T>(json::parse(body));",
        "    } catch (const json::exception& error) {",
        "        throw std::invalid_argument(error.what());",
        "    }",
        "}",
        "inline std::optional<json> dispatch(const std::string& method,",
        "                                    const std::string& path,",
        "                                    const std::string& body) {",
        "    std::smatch match;",
    ]

    for index, operation in enumerate(ir["operations"]):
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
        lines.append(f"        return rig_json::encode({namespace}::{name}({', '.join(arguments)}));")
        lines.append("    }")
    lines += [
        "    return std::nullopt;",
        "}",
        "} // namespace rig_http",
    ]
    return "\n".join(lines) + "\n"
