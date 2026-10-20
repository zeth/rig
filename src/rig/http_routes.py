"""Generate C++20 HTTP dispatch from RIG's reflected operation IR."""

import json
import re

from .ir import identifier, query_value_type, route_pattern, route_priority, validate


def generate(ir, codec_header):
    validate(ir)
    if any(operation.get("context_parameters") for operation in ir["operations"]):
        raise ValueError("HTTP route generation cannot supply context parameters")
    if not re.fullmatch(r"[A-Za-z_0-9/.-]+", codec_header):
        raise ValueError("invalid codec header path")

    names = {entry["cpp_name"] for entry in ir["types"]}

    def cpp_type(ref):
        if ref["kind"] == "builtin":
            return {"int": "int", "int64": "long long", "double": "double",
                    "bool": "bool", "string": "std::string"}[ref["name"]]
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
        "#include <charconv>",
        "#include <initializer_list>",
        "#include <map>",
        "#include <optional>",
        "#include <regex>",
        "#include <stdexcept>",
        "#include <string>",
        "#include <string_view>",
        "#include <system_error>",
        "#include <type_traits>",
        "#include <utility>",
        "#include <variant>",
        "",
        "namespace rig_http {",
        "using json = nlohmann::json;",
        "struct response { int status; json body; };",
        "inline response invalid_request(const std::string& message) {",
        '    return {400, json{{"code", "invalid_request"}, {"message", message}}};',
        "}",
        "inline void enforce_range(int value, int minimum, int maximum, const char* name) {",
        "    if (value < minimum || value > maximum)",
        '        throw std::invalid_argument(std::string("out of range: ") + name);',
        "}",
        "inline void enforce_range(const std::optional<int>& value,",
        "                          int minimum, int maximum, const char* name) {",
        "    if (value) enforce_range(*value, minimum, maximum, name);",
        "}",
        "inline void enforce_int_values(int value, std::initializer_list<int> choices, const char* name) {",
        "    for (int choice : choices) if (value == choice) return;",
        '    throw std::invalid_argument(std::string("invalid integer value: ") + name);',
        "}",
        "inline void enforce_int_values(const std::optional<int>& value,",
        "                               std::initializer_list<int> choices, const char* name) {",
        "    if (value) enforce_int_values(*value, choices, name);",
        "}",
        "inline int hex_digit(char character) {",
        "    if (character >= '0' && character <= '9') return character - '0';",
        "    if (character >= 'a' && character <= 'f') return character - 'a' + 10;",
        "    if (character >= 'A' && character <= 'F') return character - 'A' + 10;",
        "    return -1;",
        "}",
        "inline std::string decode_uri_component(std::string_view input, bool query) {",
        "    std::string result;",
        "    result.reserve(input.size());",
        "    for (std::size_t index = 0; index < input.size(); ++index) {",
        "        if (query && input[index] == '+') {",
        "            result.push_back(' ');",
        "            continue;",
        "        }",
        "        if (input[index] != '%') {",
        "            result.push_back(input[index]);",
        "            continue;",
        "        }",
        "        if (input.size() - index < 3)",
        '            throw std::invalid_argument("invalid percent escape in URL parameter");',
        "        const int high = hex_digit(input[index + 1]);",
        "        const int low = hex_digit(input[index + 2]);",
        "        if (high < 0 || low < 0)",
        '            throw std::invalid_argument("invalid percent escape in URL parameter");',
        "        result.push_back(static_cast<char>((high << 4) | low));",
        "        index += 2;",
        "    }",
        "    return result;",
        "}",
        "inline std::string decode_path_string(std::string_view input) {",
        "    return decode_uri_component(input, false);",
        "}",
        "inline std::map<std::string, std::string> decode_query(std::string_view input) {",
        "    std::map<std::string, std::string> values;",
        "    while (!input.empty()) {",
        "        const auto separator = input.find('&');",
        "        const auto entry = input.substr(0, separator);",
        "        const auto equals = entry.find('=');",
        "        auto key = decode_uri_component(entry.substr(0, equals), true);",
        "        auto value = equals == std::string_view::npos ? std::string{} :",
        "            decode_uri_component(entry.substr(equals + 1), true);",
        "        if (!values.emplace(std::move(key), std::move(value)).second)",
        '            throw std::invalid_argument("duplicate query parameter");',
        "        if (separator == std::string_view::npos) break;",
        "        input.remove_prefix(separator + 1);",
        "    }",
        "    return values;",
        "}",
        "inline int decode_int(std::string_view input, const char* message) {",
        "    int value;",
        "    const auto [end, error] = std::from_chars(input.data(), input.data() + input.size(), value);",
        "    if (error != std::errc{} || end != input.data() + input.size())",
        "        throw std::invalid_argument(message);",
        "    return value;",
        "}",
        "inline int decode_path_int(std::string_view input) {",
        '    return decode_int(input, "invalid integer path parameter");',
        "}",
        "inline int decode_query_int(std::string_view input) {",
        '    return decode_int(input, "invalid integer query parameter");',
        "}",
        "inline bool decode_query_bool(std::string_view input) {",
        '    if (input == "true") return true;',
        '    if (input == "false") return false;',
        '    throw std::invalid_argument("invalid boolean query parameter");',
        "}",
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
        "    const auto query_start = path.find('?');",
        "    const auto route_path = path.substr(0, query_start);",
    ]
    if any(item.get("in") == "query" for operation in ir["operations"]
           for item in operation["parameters"]):
        lines += [
            "    const auto query_string = query_start == std::string::npos ? std::string_view{} :",
            "        std::string_view(path).substr(query_start + 1);",
        ]
    lines.append("    std::smatch match;")
    lines.append("    (void)body;")

    # Validated overlapping routes have a strict specificity order. Keep IR
    # order for routes with the same priority or disjoint match sets.
    ordered = sorted(enumerate(ir["operations"]), key=lambda pair: route_priority(pair[1]))
    for index, operation in ordered:
        name = identifier(operation["name"])
        parameters = {identifier(item["name"]): item for item in operation["parameters"]}
        pattern, captures = route_pattern(operation["path"], parameters)
        bodies = [item for item in operation["parameters"]
                  if item["name"] not in captures and item.get("in") != "query"]
        queries = [item for item in operation["parameters"] if item.get("in") == "query"]
        if len(bodies) > 1:
            raise ValueError(f"multiple body parameters in {name}")
        lines += [
            f"    static const std::regex route_{index}({json.dumps(pattern)});",
            f'    if (method == "{operation["method"]}" && std::regex_match(route_path, match, route_{index})) {{',
        ]
        arguments = []
        decodes = (["            const auto query_values = decode_query(query_string);"]
                   if queries else [])
        for position, parameter in enumerate(operation["parameters"]):
            param_name = identifier(parameter["name"])
            param_type = cpp_type(parameter["type"])
            lines.append(f"        std::optional<{param_type}> argument_{position};")
            if param_name in captures:
                value = f"match[{captures[param_name]}].str()"
                value = (f"decode_path_int({value})" if param_type == "int"
                         else f"decode_path_string({value})")
            elif parameter.get("in") == "query":
                decodes.append(
                    f'            const auto query_{position} = query_values.find("{param_name}");'
                )
                decoder = {"int": "decode_query_int", "bool": "decode_query_bool",
                           "std::string": "std::string"}[cpp_type(query_value_type(parameter["type"]))]
                value = f"{decoder}(query_{position}->second)"
                if parameter["type"]["kind"] == "optional":
                    decodes += [
                        f"            if (query_{position} == query_values.end())",
                        f"                argument_{position}.emplace(std::nullopt);",
                        "            else",
                        f"                argument_{position}.emplace({value});",
                    ]
                    arguments.append(f"std::move(*argument_{position})")
                    continue
                decodes += [
                    f"            if (query_{position} == query_values.end())",
                    f'                throw std::invalid_argument("missing query parameter: {param_name}");',
                ]
            else:
                value = f"decode_body<{param_type}>(body)"
            decodes.append(f"            argument_{position}.emplace({value});")
            arguments.append(f"std::move(*argument_{position})")
        for position, parameter in enumerate(operation["parameters"]):
            if "range" in parameter:
                bounds = parameter["range"]
                decodes.append(
                    f'            enforce_range(*argument_{position}, '
                    f'{bounds["minimum"]}, {bounds["maximum"]}, "{parameter["name"]}");'
                )
            if "int_values" in parameter:
                values = ", ".join(str(value) for value in parameter["int_values"])
                decodes.append(
                    f'            enforce_int_values(*argument_{position}, '
                    f'{{{values}}}, "{parameter["name"]}");'
                )
        if decodes:
            lines += [
                "        try {",
                *decodes,
                "        } catch (const std::invalid_argument& error) {",
                "            return invalid_request(error.what());",
                "        } catch (const std::out_of_range& error) {",
                "            return invalid_request(error.what());",
                "        }",
            ]
        call = f"{operation['cpp_name']}({', '.join(arguments)})"
        if operation["result"]:
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
