"""Generate C++20 HTTP dispatch from RIG's reflected operation IR."""

import json
import re

from .ir import identifier, query_value_type, route_pattern, route_priority, validate
from .json_codec import cpp_literal


def generate(ir, codec_header):
    validate(ir)
    has_context = any(operation.get("context_parameters") for operation in ir["operations"])
    has_exceptions = any(error.get("exceptions") for operation in ir["operations"]
                         for error in operation.get("errors", []))
    validation = ir.get("service", {}).get("validation_error")
    internal = ir.get("service", {}).get("internal_error")
    not_allowed = ir.get("service", {}).get("method_not_allowed")
    if not re.fullmatch(r"[A-Za-z_0-9/.-]+", codec_header):
        raise ValueError("invalid codec header path")

    names = {entry["cpp_name"] for entry in ir["types"]}
    value_types = {entry["cpp_name"]: entry["fields"][0]["type"] for entry in ir["types"]
                   if entry.get("value")}

    def cpp_type(ref):
        if ref["kind"] == "builtin":
            return {"int": "int", "int64": "long long", "double": "double",
                    "bool": "bool", "string": "std::string",
                    "object": "nlohmann::json"}[ref["name"]]
        if ref["kind"] == "named":
            name = ref["name"]
            if name not in names:
                raise ValueError(f"unregistered type: {name}")
            return name
        if ref["kind"] in {"array", "optional"}:
            inner = cpp_type(ref["items"] if ref["kind"] == "array" else ref["value"])
            container = "vector" if ref["kind"] == "array" else "optional"
            return f"std::{container}<{inner}>"
        if ref["kind"] == "map":
            return f"std::map<std::string, {cpp_type(ref['values'])}>"
        if ref["kind"] == "variant":
            return f"std::variant<{', '.join(cpp_type(item) for item in ref['alternatives'])}>"
        raise ValueError(f"unsupported operation parameter type: {ref['kind']}")

    lines = [
        "// Generated from RIG IR; do not edit.",
        "#pragma once",
        f'#include "{codec_header}"',
        "#include <charconv>",
        "#include <exception>",
        "#include <initializer_list>",
        "#include <limits>",
        "#include <map>",
        "#include <optional>",
        *(["#include <set>"] if not_allowed else []),
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
        "struct response {",
        "    int status;",
        "    json body;",
        "    std::string_view operation;",
        "    // The methods the path accepts, for a 405's Allow header; empty otherwise.",
        "    std::string allow = {};",
        "};",
        *([
            "// The error passed to rig_error_body for a 405.",
            "struct method_not_allowed : std::runtime_error {",
            "    using std::runtime_error::runtime_error;",
            "};",
        ] if not_allowed else []),
        *([
            "// The application supplies rig_error_body, found by argument-dependent",
            "// lookup, to build each declared error body from an exception.",
            "template <typename Body, typename Error>",
            "json encode_error(int status, const Error& error) {",
            "    const Body body = rig_error_body(std::type_identity<Body>{}, status, error);",
            "    return rig_json::encode(body);",
            "}",
        ] if has_exceptions or validation or internal or not_allowed else []),
        "inline response invalid_request(const std::exception& error, std::string_view operation) {",
        *([f"    return {{400, encode_error<{cpp_type(validation['type'])}>(400, error), operation}};"]
          if validation else
          ['    return {400, json{{"code", "invalid_request"}, {"message", error.what()}}, operation};']),
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
        "inline void enforce_string_values(const std::string& value,",
        "                                  std::initializer_list<std::string_view> choices, const char* name) {",
        "    for (auto choice : choices) if (value == choice) return;",
        '    throw std::invalid_argument(std::string("invalid value: ") + name);',
        "}",
        "inline void enforce_string_values(const std::optional<std::string>& value,",
        "                                  std::initializer_list<std::string_view> choices, const char* name) {",
        "    if (value) enforce_string_values(*value, choices, name);",
        "}",
        "inline void enforce_length(const std::string& value, std::size_t minimum, std::size_t maximum,",
        "                           const char* name) {",
        "    if (value.size() < minimum || value.size() > maximum)",
        '        throw std::invalid_argument(std::string("invalid length: ") + name);',
        "}",
        "inline void enforce_length(const std::optional<std::string>& value, std::size_t minimum,",
        "                           std::size_t maximum, const char* name) {",
        "    if (value) enforce_length(*value, minimum, maximum, name);",
        "}",
        "inline void enforce_pattern(const std::string& value, const std::regex& pattern, const char* name) {",
        "    if (!std::regex_search(value, pattern))",
        '        throw std::invalid_argument(std::string("invalid format: ") + name);',
        "}",
        "inline void enforce_pattern(const std::optional<std::string>& value, const std::regex& pattern,",
        "                            const char* name) {",
        "    if (value) enforce_pattern(*value, pattern, name);",
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
        "inline long long decode_query_int64(std::string_view input) {",
        "    long long value;",
        "    const auto [end, error] = std::from_chars(input.data(), input.data() + input.size(), value);",
        "    if (error != std::errc{} || end != input.data() + input.size())",
        '        throw std::invalid_argument("invalid integer query parameter");',
        "    return value;",
        "}",
        "inline bool decode_query_bool(std::string_view input) {",
        '    if (input == "true" || input == "1") return true;',
        '    if (input == "false" || input == "0") return false;',
        '    throw std::invalid_argument("invalid boolean query parameter");',
        "}",
        "template <typename T> T decode_body(const std::string& body) {",
        "    try {",
        "        return rig_json::decode<T>(json::parse(body));",
        "    } catch (const json::exception& error) {",
        "        throw std::invalid_argument(error.what());",
        "    }",
        "}",
        *(["template <typename Context>"] if has_context else []),
        "inline std::optional<response> dispatch(const std::string& method,",
        "                                    const std::string& path,",
        "                                    const std::string& body" +
        (", Context& context) {" if has_context else ") {"),
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
        if "host_response" in operation:
            # Matching it here keeps a less specific generated route from taking it.
            lines += [
                f"    static const std::regex route_{index}({json.dumps(pattern)});",
                f'    if (method == "{operation["method"]}" && '
                f"std::regex_match(route_path, route_{index}))",
                f"        return std::nullopt;  // {name} is served by the host",
            ]
            continue
        bodies = [item for item in operation["parameters"]
                  if item["name"] not in captures and item.get("in") not in ("query", "header")]
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
                query_ref = query_value_type(parameter["type"])
                wrapped = value_types.get(query_ref["name"]) if query_ref["kind"] == "named" else None
                if query_ref["kind"] == "variant":
                    # Every alternative decodes from the query string as JSON text.
                    decoder = "std::string"
                else:
                    decoder = {"int": "decode_query_int", "long long": "decode_query_int64",
                               "bool": "decode_query_bool", "std::string": "std::string"}[
                        cpp_type(wrapped or query_ref)]
                value = f"{decoder}(query_{position}->second)"
                if query_ref["kind"] == "variant":
                    value = f"rig_json::decode<{cpp_type(query_ref)}>(json({value}))"
                if wrapped:
                    # The value type's codec applies its constraints.
                    value = f"rig_json::decode<{query_ref['name']}>(json({value}))"
                if parameter["type"]["kind"] == "optional":
                    decodes += [
                        f"            if (query_{position} == query_values.end())",
                        f"                argument_{position}.emplace(std::nullopt);",
                        "            else",
                        f"                argument_{position}.emplace({value});",
                    ]
                    arguments.append(f"std::move(*argument_{position})")
                    continue
                if "default" in parameter:
                    decodes += [
                        f"            if (query_{position} == query_values.end())",
                        f"                argument_{position}.emplace({cpp_literal(parameter['default'])});",
                        "            else",
                        f"                argument_{position}.emplace({value});",
                    ]
                    arguments.append(f"std::move(*argument_{position})")
                    continue
                decodes += [
                    f"            if (query_{position} == query_values.end())",
                    f'                throw std::invalid_argument("missing query parameter: {param_name}");',
                ]
            elif parameter["type"]["kind"] == "optional":
                # An optional body may be empty.
                inner = cpp_type(parameter["type"]["value"])
                value = (f"body.empty() ? {param_type}{{}} : "
                         f"{param_type}(decode_body<{inner}>(body))")
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
            if "minimum" in parameter:
                decodes.append(
                    f'            enforce_range(*argument_{position}, {parameter["minimum"]}, '
                    f'std::numeric_limits<int>::max(), "{parameter["name"]}");'
                )
            if "string_values" in parameter:
                values = ", ".join(json.dumps(value) for value in parameter["string_values"])
                decodes.append(
                    f'            enforce_string_values(*argument_{position}, '
                    f'{{{values}}}, "{parameter["name"]}");'
                )
            if "pattern" in parameter:
                decodes += [
                    f"            static const std::regex pattern_{position}({json.dumps(parameter['pattern'])});",
                    f'            enforce_pattern(*argument_{position}, pattern_{position}, "{parameter["name"]}");',
                ]
            if "min_length" in parameter or "max_length" in parameter:
                maximum = parameter.get("max_length", "std::numeric_limits<std::size_t>::max()")
                decodes.append(
                    f'            enforce_length(*argument_{position}, {parameter.get("min_length", 0)}, '
                    f'{maximum}, "{parameter["name"]}");'
                )
        if decodes:
            lines += [
                "        try {",
                *decodes,
                "        } catch (const std::invalid_argument& error) {",
                f'            return invalid_request(error, "{name}");',
                "        } catch (const std::out_of_range& error) {",
                f'            return invalid_request(error, "{name}");',
                "        }",
            ]
        contexts = {item["position"]: f'context.{identifier(item["name"])}'
                    for item in operation.get("context_parameters", [])}
        supplied = iter(arguments)
        call_arguments = [contexts[index] if index in contexts else next(supplied)
                          for index in range(len(arguments) + len(contexts))]
        call = f"{operation['cpp_name']}({', '.join(call_arguments)})"
        success = operation.get("success_status", 200)
        if operation["result"]:
            success_type = cpp_type(operation["returns"])
            invoke = [
                f"        const auto outcome = {call};",
                f'        return std::visit([](const auto& value) -> response {{',
                "            using value_type = std::decay_t<decltype(value)>;",
                f"            if constexpr (std::is_same_v<value_type, {success_type}>) {{",
                f'                return {{{success}, rig_json::encode(value), "{name}"}};',
                "            } else {",
                f'                return {{value_type::status, rig_json::encode(value.body), "{name}"}};',
                "            }",
                "        }, outcome.value());",
            ]
        else:
            invoke = [f'        return response{{{success}, rig_json::encode({call}), "{name}"}};']
        mapped = [(error["status"], cpp_type(error["type"]), exception)
                  for error in operation.get("errors", [])
                  for exception in error.get("exceptions", [])]
        # The service's internal error catches whatever the operation's own
        # mapping leaves, unless the operation already maps std::exception.
        if internal and "std::exception" not in [exception for _, _, exception in mapped]:
            mapped.append((500, cpp_type(internal["type"]), "std::exception"))
        if mapped:
            lines += ["        try {", *("    " + line for line in invoke)]
            for status, body_type, exception in mapped:
                lines += [
                    f"        }} catch (const {exception}& error) {{",
                    f'            return response{{{status}, encode_error<{body_type}>({status}, error), "{name}"}};',
                ]
            lines.append("        }")
        else:
            lines += invoke
        lines.append("    }")
    if not_allowed:
        # No operation took the method, so the path either names none or names
        # some with other methods. Host-served operations count, as they are
        # declared too. Operations with the same path pattern share one check.
        methods_by_pattern = {}
        for _, operation in ordered:
            parameters = {identifier(item["name"]): item for item in operation["parameters"]}
            pattern, _ = route_pattern(operation["path"], parameters)
            methods_by_pattern.setdefault(pattern, set()).add(operation["method"])
        lines.append("    std::set<std::string_view> allowed;")
        for position, (pattern, methods) in enumerate(methods_by_pattern.items()):
            listed = ", ".join(json.dumps(method) for method in sorted(methods))
            lines += [
                f"    static const std::regex path_{position}({json.dumps(pattern)});",
                f"    if (std::regex_match(route_path, path_{position})) "
                f"allowed.insert({{{listed}}});",
            ]
        lines += [
            "    if (!allowed.empty()) {",
            "        std::string allow;",
            "        for (const auto allowed_method : allowed) {",
            '            if (!allow.empty()) allow += ", ";',
            "            allow += allowed_method;",
            "        }",
            f'        const method_not_allowed error("method not allowed");',
            f"        return response{{405, encode_error<{cpp_type(not_allowed['type'])}>(405, error), "
            '"", std::move(allow)};',
            "    }",
        ]
    lines += [
        "    return std::nullopt;",
        "}",
        "// Whether the operation dispatch would select for this request is RIG_PUBLIC,",
        "// so the hosting server can skip authentication for it.",
        "inline bool is_public(const std::string& method, const std::string& path) {",
    ]
    # Routes after the last public one in dispatch order can only answer false.
    public_positions = [position for position, (_, operation) in enumerate(ordered)
                        if operation.get("public")]
    if public_positions:
        lines.append("    const auto route_path = path.substr(0, path.find('?'));")
        for index, operation in [pair for pair in ordered][:public_positions[-1] + 1]:
            parameters = {identifier(item["name"]): item for item in operation["parameters"]}
            pattern, _ = route_pattern(operation["path"], parameters)
            verdict = "true" if operation.get("public") else "false"
            lines += [
                f"    static const std::regex route_{index}({json.dumps(pattern)});",
                f'    if (method == "{operation["method"]}" && '
                f"std::regex_match(route_path, route_{index})) return {verdict};",
            ]
    else:
        lines += ["    (void)method;", "    (void)path;"]
    lines += [
        "    return false;",
        "}",
        "} // namespace rig_http",
    ]
    return "\n".join(lines) + "\n"
