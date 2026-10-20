"""Validation and shared route rules for RIG IR version 3."""

import re
from collections import Counter


VERSION = 3
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
                member = _object(member, member_location, ("name", "type"))
                member_name = _name(member["name"], f"{member_location}.name")
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
    routes = set()
    for index, operation in enumerate(operations):
        location = f"$.operations[{index}]"
        operation = _object(
            operation, location,
            ("name", "cpp_name", "method", "path", "parameters", "returns"), ("errors",),
        )
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
            parameter = _object(parameter, parameter_location, ("name", "type"))
            parameter_name = _name(parameter["name"], f"{parameter_location}.name")
            _unique(parameter_names, parameter_name, parameter_location, "parameter")
            type_ref(parameter["type"], f"{parameter_location}.type")
            by_name[parameter_name] = parameter
        type_ref(operation["returns"], f"{location}.returns")
        path = operation["path"]
        _, captures = route_pattern(path, by_name)
        route = (method, path)
        if route in routes:
            raise ValueError(f"{location}: duplicate route: {method} {path}")
        routes.add(route)
        bodies = parameter_names - captures.keys()
        if len(bodies) > 1:
            raise ValueError(f"{location}: operation {name} has multiple body parameters")
        if bodies and method in ("GET", "DELETE"):
            raise ValueError(f"{location}: operation {name} has a body with {method}")
        statuses = set()
        for error_index, error in enumerate(_array(operation.get("errors", []), f"{location}.errors")):
            error_location = f"{location}.errors[{error_index}]"
            error = _object(error, error_location, ("status", "type"))
            status = error["status"]
            if type(status) is not int or not 400 <= status <= 599:
                raise ValueError(f"{error_location}: invalid error status in {name}: {status!r}")
            _unique(statuses, status, error_location, f"response status in {name}")
            type_ref(error["type"], f"{error_location}.type")
    return ir
