#!/usr/bin/env python3
"""Generate C++20 HTTP dispatch from RIG's reflected operation IR."""

import argparse
import json
import re
import sys

from .json_codec import identifier
from .openapi import convert


PARAMETER = re.compile(r"\{([A-Za-z_][A-Za-z_0-9]*)\}\Z")
LITERAL = re.compile(r"[A-Za-z0-9._~-]+\Z")


def route_pattern(path, parameters):
    if not path.startswith("/") or "//" in path or (path != "/" and path.endswith("/")):
        raise ValueError(f"unsupported route path: {path}")
    if path == "/":
        return "^/$", {}
    regex = ["^"]
    captures = {}
    for segment in path.split("/")[1:]:
        regex.append("/")
        placeholder = PARAMETER.fullmatch(segment)
        if placeholder:
            name = placeholder[1]
            if name in captures:
                raise ValueError(f"duplicate route parameter: {name}")
            ref = parameters[name]["type"]
            if ref == {"kind": "builtin", "name": "int"}:
                regex.append("([0-9]+)")
            elif ref == {"kind": "builtin", "name": "string"}:
                regex.append("([^/]+)")
            else:
                raise ValueError(f"unsupported path parameter type: {name}")
            captures[name] = len(captures) + 1
        elif LITERAL.fullmatch(segment):
            regex.append(re.escape(segment))
        else:
            raise ValueError(f"unsupported route segment: {segment}")
    regex.append("$")
    return "".join(regex), captures


def generate(ir, namespace, codec_header):
    # Use the same contract validation as the OpenAPI output.
    convert(ir)
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
        if len(parameters) != len(operation["parameters"]):
            raise ValueError(f"duplicate parameter in {name}")
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--codec-header", required=True)
    args = parser.parse_args()
    try:
        sys.stdout.write(generate(json.load(sys.stdin), args.namespace, args.codec_header))
    except (KeyError, ValueError) as error:
        print(f"RIG HTTP route generation failed: {error}", file=sys.stderr)
        sys.exit(1)
