"""Validation and shared route rules for RIG IR version 7."""

import re
from collections import Counter


VERSION = 7
BUILTINS = {"int", "bool", "string"}
METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z_0-9]*\Z")
PARAMETER = re.compile(r"\{([A-Za-z_][A-Za-z_0-9]*)\}\Z")
LITERAL = re.compile(r"[A-Za-z0-9._~-]+\Z")


def identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError(f"invalid C++ identifier: {value!r}")
    return value


def cpp_name(value):
    if not isinstance(value, str) or not value:
        raise ValueError(f"invalid qualified C++ name: {value!r}")
    try:
        for part in value.split("::"):
            identifier(part)
    except ValueError:
        raise ValueError(f"invalid qualified C++ name: {value!r}") from None
    return value


def public_names(qualified_names):
    """Use short names unless another declaration has the same short name."""
    names = list(qualified_names)
    counts = Counter(name.rsplit("::", 1)[-1] for name in names)
    return {
        name: (short if counts[short] == 1 else name.replace("::", "."))
        for name in names
        for short in [name.rsplit("::", 1)[-1]]
    }


def _object(value, location, required, optional=()):
    if not isinstance(value, dict):
        raise ValueError(f"{location}: expected object")
    missing = set(required) - value.keys()
    if missing:
        raise ValueError(f"{location}: missing {sorted(missing)[0]}")
    unknown = value.keys() - set(required) - set(optional)
    if unknown:
        raise ValueError(f"{location}: unknown key {sorted(unknown)[0]}")
    return value


def _array(value, location):
    if not isinstance(value, list):
        raise ValueError(f"{location}: expected array")
    return value


def _name(value, location):
    try:
        return identifier(value)
    except ValueError as error:
        raise ValueError(f"{location}: {error}") from None


def _unique(names, name, location, label):
    if name in names:
        raise ValueError(f"{location}: duplicate {label}: {name}")
    names.add(name)


def route_pattern(path, parameters):
    """Return the regex and capture positions for a supported HTTP route."""
    if not isinstance(path, str) or not path.startswith("/") or "//" in path or (
        path != "/" and path.endswith("/")
    ):
        raise ValueError(f"unsupported route path: {path!r}")
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
            if name not in parameters:
                raise ValueError(f"route {path} has unbound placeholders: {name}")
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


def route_segments(path, parameters):
    """Return validated route segments as (specificity, literal) pairs."""
    route_pattern(path, parameters)
    segments = []
    for segment in path.split("/")[1:]:
        if not segment:
            continue
        placeholder = PARAMETER.fullmatch(segment)
        if placeholder:
            kind = parameters[placeholder[1]]["type"]["name"]
            segments.append((1 if kind == "int" else 2, ""))
        else:
            segments.append((0, segment))
    return tuple(segments)


def route_priority(operation):
    parameters = {item["name"]: item for item in operation["parameters"]}
    return tuple(kind for kind, _ in route_segments(operation["path"], parameters))


def request_needs_decoding(operation):
    """Whether route input can fail conversion before calling the operation."""
    return bool(operation["parameters"])


def query_value_type(ref):
    """Return the scalar type used for a required or optional query value."""
    return ref["value"] if ref["kind"] == "optional" else ref


def _segments_overlap(left, right):
    if len(left) != len(right):
        return False
    for (left_kind, left_value), (right_kind, right_value) in zip(left, right):
        if left_kind == right_kind == 0 and left_value != right_value:
            return False
        if left_kind == 0 and right_kind == 1 and not re.fullmatch(r"[0-9]+", left_value):
            return False
        if right_kind == 0 and left_kind == 1 and not re.fullmatch(r"[0-9]+", right_value):
            return False
    return True


def _same_template(left, right):
    return all(
        (a_kind == b_kind == 0 and a_value == b_value) or
        (a_kind != 0 and b_kind != 0)
        for (a_kind, a_value), (b_kind, b_value) in zip(left, right)
    )


def _more_specific(left, right):
    kinds = [(a[0], b[0]) for a, b in zip(left, right)]
    return all(a <= b for a, b in kinds) and any(a < b for a, b in kinds)


def validate(document):
    """Validate an IR document and return it unchanged for the generators."""
    ir = _object(document, "$", ("ir_version", "types", "operations"))
    if type(ir["ir_version"]) is not int or ir["ir_version"] != VERSION:
        raise ValueError(f"unsupported RIG IR version: {ir['ir_version']!r}")
    entries = _array(ir["types"], "$.types")
    operations = _array(ir["operations"], "$.operations")

    names = set()
    for index, entry in enumerate(entries):
        location = f"$.types[{index}]"
        entry = _object(entry, location, ("kind", "name", "cpp_name"), ("fields", "values"))
        kind = entry["kind"]
        if kind not in ("record", "enum"):
            raise ValueError(f"{location}: unsupported declaration kind: {kind!r}")
        name = _name(entry["name"], f"{location}.name")
        qualified = cpp_name(entry["cpp_name"])
        if qualified.rsplit("::", 1)[-1] != name:
            raise ValueError(f"{location}: type name does not match cpp_name")
        _unique(names, qualified, location, "type name")
        member_key = "fields" if kind == "record" else "values"
        _object(entry, location, ("kind", "name", "cpp_name", member_key))
        members = _array(entry[member_key], f"{location}.{member_key}")
        member_names = set()
        for member_index, member in enumerate(members):
            member_location = f"{location}.{member_key}[{member_index}]"
            if kind == "record":
                member = _object(member, member_location, ("name", "type"), ("bool_value",))
                member_name = _name(member["name"], f"{member_location}.name")
                if "bool_value" in member:
                    if type(member["bool_value"]) is not bool or member["type"] != {
                        "kind": "builtin", "name": "bool"
                    }:
                        raise ValueError(f"{member_location}.bool_value: requires a bool field")
                label = "field"
            else:
                member_name = _name(member, member_location)
                label = "enum value"
            _unique(member_names, member_name, member_location, label)

    def type_ref(ref, location):
        ref = _object(ref, location, ("kind",), ("name", "items", "value"))
        kind = ref["kind"]
        if kind == "builtin":
            _object(ref, location, ("kind", "name"))
            if not isinstance(ref["name"], str) or ref["name"] not in BUILTINS:
                raise ValueError(f"{location}: unsupported builtin type: {ref['name']!r}")
        elif kind == "named":
            _object(ref, location, ("kind", "name"))
            name = cpp_name(ref["name"])
            if name not in names:
                raise ValueError(f"{location}: unregistered type: {name}")
        elif kind in ("array", "optional"):
            child = "items" if kind == "array" else "value"
            _object(ref, location, ("kind", child))
            type_ref(ref[child], f"{location}.{child}")
        else:
            raise ValueError(f"{location}: unsupported type kind: {kind!r}")

    for index, entry in enumerate(entries):
        if entry["kind"] == "record":
            for member_index, field in enumerate(entry["fields"]):
                type_ref(field["type"], f"$.types[{index}].fields[{member_index}].type")

    operation_names = set()
    routes = {}
    for index, operation in enumerate(operations):
        location = f"$.operations[{index}]"
        operation = _object(
            operation, location,
            ("name", "cpp_name", "method", "path", "parameters", "returns"),
            ("errors", "summary", "description", "response_description"),
        )
        for key in ("summary", "description", "response_description"):
            if key in operation and (not isinstance(operation[key], str) or not operation[key]):
                raise ValueError(f"{location}.{key}: expected nonempty text")
        name = _name(operation["name"], f"{location}.name")
        qualified = cpp_name(operation["cpp_name"])
        if qualified.rsplit("::", 1)[-1] != name:
            raise ValueError(f"{location}: operation name does not match cpp_name")
        _unique(operation_names, qualified, location, "operation name")
        method = operation["method"]
        if not isinstance(method, str) or method not in METHODS:
            raise ValueError(f"{location}.method: unsupported HTTP method: {method!r}")
        parameters = _array(operation["parameters"], f"{location}.parameters")
        parameter_names = set()
        by_name = {}
        for parameter_index, parameter in enumerate(parameters):
            parameter_location = f"{location}.parameters[{parameter_index}]"
            parameter = _object(parameter, parameter_location, ("name", "type"), ("in", "range"))
            parameter_name = _name(parameter["name"], f"{parameter_location}.name")
            _unique(parameter_names, parameter_name, parameter_location, "parameter")
            type_ref(parameter["type"], f"{parameter_location}.type")
            if "range" in parameter:
                bounds = _object(parameter["range"], f"{parameter_location}.range",
                                 ("minimum", "maximum"))
                if any(type(bounds[key]) is not int for key in ("minimum", "maximum")):
                    raise ValueError(f"{parameter_location}.range: bounds must be integers")
                if any(not -(2 ** 31) <= bounds[key] < 2 ** 31
                       for key in ("minimum", "maximum")):
                    raise ValueError(f"{parameter_location}.range: bounds must fit C++ int")
                if bounds["minimum"] > bounds["maximum"]:
                    raise ValueError(f"{parameter_location}.range: minimum exceeds maximum")
                if query_value_type(parameter["type"]) != {"kind": "builtin", "name": "int"}:
                    raise ValueError(f"{parameter_location}.range: requires int or optional<int>")
            if "in" in parameter:
                if parameter["in"] != "query":
                    raise ValueError(f"{parameter_location}.in: unsupported parameter location")
                if query_value_type(parameter["type"])["kind"] != "builtin":
                    raise ValueError(f"{parameter_location}: query parameter must be scalar or optional scalar")
            by_name[parameter_name] = parameter
        type_ref(operation["returns"], f"{location}.returns")
        path = operation["path"]
        _, captures = route_pattern(path, by_name)
        for parameter in parameters:
            if parameter.get("in") == "query" and parameter["name"] in captures:
                raise ValueError(f"{location}: query parameter is also a path placeholder")
        segments = route_segments(path, by_name)
        route = (method, path)
        if route in routes:
            raise ValueError(f"{location}: duplicate route: {method} {path}")
        for (existing_method, existing_path), existing_segments in routes.items():
            if method != existing_method or not _segments_overlap(segments, existing_segments):
                continue
            if _same_template(segments, existing_segments) or not (
                _more_specific(segments, existing_segments) or
                _more_specific(existing_segments, segments)
            ):
                raise ValueError(
                    f"{location}: ambiguous routes: {method} {existing_path} and {method} {path}"
                )
        routes[route] = segments
        bodies = {
            parameter["name"] for parameter in parameters
            if parameter["name"] not in captures and parameter.get("in") != "query"
        }
        if len(bodies) > 1:
            raise ValueError(f"{location}: operation {name} has multiple body parameters")
        if bodies and method in ("GET", "DELETE"):
            raise ValueError(f"{location}: operation {name} has a body with {method}")
        statuses = set()
        for error_index, error in enumerate(_array(operation.get("errors", []), f"{location}.errors")):
            error_location = f"{location}.errors[{error_index}]"
            error = _object(error, error_location, ("status", "type"), ("description",))
            status = error["status"]
            if type(status) is not int or not 400 <= status <= 599:
                raise ValueError(f"{error_location}: invalid error status in {name}: {status!r}")
            _unique(statuses, status, error_location, f"response status in {name}")
            if "description" in error and (
                not isinstance(error["description"], str) or not error["description"]
            ):
                raise ValueError(f"{error_location}.description: expected nonempty text")
            type_ref(error["type"], f"{error_location}.type")
    return ir
