"""Validation and shared route rules for RIG IR version 12."""

import re
from collections import Counter


VERSION = 12
BUILTINS = {"int", "int64", "double", "bool", "string", "object"}
METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z_0-9]*\Z")
PARAMETER = re.compile(r"\{([A-Za-z_][A-Za-z_0-9]*)\}\Z")
LITERAL = re.compile(r"[A-Za-z0-9._~-]+\Z")
HEADER = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*\Z")
MEDIA_TYPE = re.compile(r"[a-z]+/[A-Za-z0-9][A-Za-z0-9.+-]*\Z")


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


FORMAT = re.compile(r"[a-z0-9][a-z0-9-]*\Z")
STRING = {"kind": "builtin", "name": "string"}
INTEGERS = ({"kind": "builtin", "name": "int"}, {"kind": "builtin", "name": "int64"})


def _value_constraints(item, ref, location):
    """Check format, length and default against the scalar type they describe."""
    if "format" in item:
        if not isinstance(item["format"], str) or not FORMAT.fullmatch(item["format"]):
            raise ValueError(f"{location}.format: expected a format name")
        if ref != STRING and ref not in INTEGERS:
            raise ValueError(f"{location}.format: requires a string or integer")
    if "pattern" in item:
        if not isinstance(item["pattern"], str) or not item["pattern"]:
            raise ValueError(f"{location}.pattern: expected a regular expression")
        if ref != STRING:
            raise ValueError(f"{location}.pattern: requires a string")
    for key in ("min_length", "max_length"):
        if key in item:
            if type(item[key]) is not int or item[key] < 0:
                raise ValueError(f"{location}.{key}: expected a non-negative integer")
            if ref != STRING:
                raise ValueError(f"{location}.{key}: requires a string")
    if item.get("min_length", 0) > item.get("max_length", item.get("min_length", 0)):
        raise ValueError(f"{location}: min_length exceeds max_length")
    if "default" in item:
        value = item["default"]
        expected = {"bool": bool, "int": int, "int64": int, "string": str}.get(
            ref.get("name") if ref.get("kind") == "builtin" else None)
        if expected is None or type(value) is not expected:
            raise ValueError(f"{location}.default: does not match the value type")
        for choices in ("string_values", "int_values"):
            if choices in item and value not in item[choices]:
                raise ValueError(f"{location}.default: not one of the {choices}")


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
    """Whether generated dispatch decodes route input that can fail conversion."""
    return bool(operation["parameters"]) and "host_response" not in operation


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
    ir = _object(document, "$", ("ir_version", "types", "operations"), ("service",))
    if type(ir["ir_version"]) is not int or ir["ir_version"] != VERSION:
        raise ValueError(f"unsupported RIG IR version: {ir['ir_version']!r}")
    entries = _array(ir["types"], "$.types")
    operations = _array(ir["operations"], "$.operations")
    if "service" in ir:
        service = _object(ir["service"], "$.service", ("title", "version", "servers"),
                          ("bearer_auth", "validation_error", "unauthorized",
                           "internal_error", "method_not_allowed"))
        for key in ("title", "version"):
            if not isinstance(service[key], str) or not service[key]:
                raise ValueError(f"$.service.{key}: expected nonempty text")
        servers = _array(service["servers"], "$.service.servers")
        for index, url in enumerate(servers):
            if not isinstance(url, str) or not url:
                raise ValueError(f"$.service.servers[{index}]: expected nonempty URL")
        if "bearer_auth" in service:
            auth = _object(service["bearer_auth"], "$.service.bearer_auth", ("name", "format"))
            _name(auth["name"], "$.service.bearer_auth.name")
            if not isinstance(auth["format"], str) or not auth["format"]:
                raise ValueError("$.service.bearer_auth.format: expected nonempty text")

    names = set()
    for index, entry in enumerate(entries):
        location = f"$.types[{index}]"
        entry = _object(entry, location, ("kind", "name", "cpp_name"),
                        ("fields", "values", "open", "inline", "description", "value", "base",
                         "min_properties"))
        kind = entry["kind"]
        if kind not in ("record", "enum"):
            raise ValueError(f"{location}: unsupported declaration kind: {kind!r}")
        name = _name(entry["name"], f"{location}.name")
        qualified = cpp_name(entry["cpp_name"])
        if qualified.rsplit("::", 1)[-1] != name:
            raise ValueError(f"{location}: type name does not match cpp_name")
        _unique(names, qualified, location, "type name")
        member_key = "fields" if kind == "record" else "values"
        _object(entry, location, ("kind", "name", "cpp_name", member_key),
                ("open", "inline", "description", "value", "base", "min_properties")
                if kind == "record" else ())
        if "min_properties" in entry and (
            type(entry["min_properties"]) is not int or entry["min_properties"] < 0
        ):
            raise ValueError(f"{location}.min_properties: expected a non-negative integer")
        if "description" in entry and (
            not isinstance(entry["description"], str) or not entry["description"]
        ):
            raise ValueError(f"{location}.description: expected nonempty text")
        if "open" in entry and type(entry["open"]) is not bool:
            raise ValueError(f"{location}.open: expected boolean")
        if "inline" in entry and type(entry["inline"]) is not bool:
            raise ValueError(f"{location}.inline: expected boolean")
        members = _array(entry[member_key], f"{location}.{member_key}")
        member_names = set()
        for member_index, member in enumerate(members):
            member_location = f"{location}.{member_key}[{member_index}]"
            if kind == "record":
                member = _object(member, member_location, ("name", "type"),
                                 ("bool_value", "description", "minimum",
                                  "omit_empty", "nullable", "string_values", "write_only",
                                  "format", "min_length", "max_length", "default", "pattern"))
                member_name = _name(member["name"], f"{member_location}.name")
                if "bool_value" in member:
                    if type(member["bool_value"]) is not bool or member["type"] != {
                        "kind": "builtin", "name": "bool"
                    }:
                        raise ValueError(f"{member_location}.bool_value: requires a bool field")
                if "description" in member and not isinstance(member["description"], str):
                    raise ValueError(f"{member_location}.description: expected string")
                if "minimum" in member:
                    ref = member["type"]
                    # An omittable optional carries the bound on its value schema.
                    if member.get("omit_empty") and not member.get("nullable") and (
                        isinstance(ref, dict) and ref.get("kind") == "optional"
                    ):
                        ref = ref.get("value")
                    if type(member["minimum"]) is not int or ref != {
                        "kind": "builtin", "name": "int"
                    }:
                        raise ValueError(f"{member_location}.minimum: requires an int field")
                if "string_values" in member:
                    choices = _array(member["string_values"],
                                     f"{member_location}.string_values")
                    ref = member["type"]
                    # Omittable and nullable fields wrap the string in one optional each.
                    layers = int(bool(member.get("omit_empty"))) + int(bool(member.get("nullable")))
                    for _ in range(layers):
                        if isinstance(ref, dict) and ref.get("kind") == "optional":
                            ref = ref.get("value")
                    if ref != {"kind": "builtin", "name": "string"}:
                        raise ValueError(f"{member_location}.string_values: requires a string field")
                    if not 1 <= len(choices) <= 16 or any(
                        not isinstance(choice, str) or not choice or len(choice.encode()) >= 64
                        for choice in choices
                    ) or len(set(choices)) != len(choices):
                        raise ValueError(f"{member_location}.string_values: expected unique nonempty strings")
                value_ref = member["type"]
                if member.get("omit_empty") and not member.get("nullable") and (
                    isinstance(value_ref, dict) and value_ref.get("kind") == "optional"
                ):
                    value_ref = value_ref.get("value")
                if isinstance(value_ref, dict):
                    _value_constraints(member, value_ref, member_location)
                if "default" in member and member.get("omit_empty"):
                    raise ValueError(f"{member_location}.default: a defaulted field is not optional")
                if "write_only" in member and member["write_only"] is not True:
                    raise ValueError(f"{member_location}.write_only: expected true")
                for option in ("omit_empty", "nullable"):
                    if option in member:
                        ref = member["type"]
                        if member[option] is not True or not isinstance(ref, dict) or (
                            ref.get("kind") != "optional"
                        ):
                            raise ValueError(f"{member_location}.{option}: requires an optional field")
                if "nullable" in member:
                    inner = member["type"].get("value")
                    if "omit_empty" in member:
                        if not isinstance(inner, dict) or inner.get("kind") != "optional":
                            raise ValueError(f"{member_location}: omittable nullable requires nested optional")
                        inner = inner.get("value")
                    if not isinstance(inner, dict) or (
                        inner.get("kind") != "builtin" and "omit_empty" not in member
                    ):
                        # A required nullable record or array is just a plain optional.
                        raise ValueError(f"{member_location}.nullable: requires an optional builtin")
                label = "field"
            else:
                member_name = _name(member, member_location)
                label = "enum value"
            _unique(member_names, member_name, member_location, label)

    def type_ref(ref, location):
        ref = _object(ref, location, ("kind",), ("name", "items", "value", "values", "alternatives"))
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
        elif kind in ("array", "optional", "map"):
            child = {"array": "items", "optional": "value", "map": "values"}[kind]
            _object(ref, location, ("kind", child))
            type_ref(ref[child], f"{location}.{child}")
        elif kind == "variant":
            _object(ref, location, ("kind", "alternatives"))
            alternatives = _array(ref["alternatives"], f"{location}.alternatives")
            if len(alternatives) < 2:
                raise ValueError(f"{location}.alternatives: expected at least two")
            for index, alternative in enumerate(alternatives):
                type_ref(alternative, f"{location}.alternatives[{index}]")
                if alternative["kind"] == "optional" or alternatives.index(alternative) != index:
                    raise ValueError(f"{location}.alternatives[{index}]: expected a distinct, "
                                     "non-optional alternative")
        else:
            raise ValueError(f"{location}: unsupported type kind: {kind!r}")

    for index, entry in enumerate(entries):
        if entry["kind"] == "record":
            for member_index, field in enumerate(entry["fields"]):
                type_ref(field["type"], f"$.types[{index}].fields[{member_index}].type")
    records = {entry["cpp_name"]: entry for entry in entries if entry["kind"] == "record"}
    for index, entry in enumerate(entries):
        location = f"$.types[{index}]"
        if entry.get("value") is not None:
            if entry["value"] is not True:
                raise ValueError(f"{location}.value: expected true")
            if len(entry["fields"]) != 1 or entry["fields"][0].get("omit_empty") or "base" in entry:
                raise ValueError(f"{location}: a value type has exactly one required field "
                                 "and no base")
        if "base" in entry:
            seen = {entry["cpp_name"]}
            base = entry["base"]
            while base is not None:
                if base not in records or records[base].get("value"):
                    raise ValueError(f"{location}.base: expected a registered record: {base}")
                if base in seen:
                    raise ValueError(f"{location}.base: records extend each other in a cycle")
                seen.add(base)
                inherited = {field["name"] for field in records[base]["fields"]}
                for field in entry["fields"]:
                    if field["name"] in inherited:
                        raise ValueError(f"{location}: field {field['name']} hides a base field")
                base = records[base].get("base")

    def scalar(ref):
        """The scalar a value type wraps, or the reference itself."""
        if ref.get("kind") == "named" and records.get(ref["name"], {}).get("value"):
            return records[ref["name"]]["fields"][0]["type"]
        return ref

    for key in ("validation_error", "unauthorized", "internal_error", "method_not_allowed"):
        if key in ir.get("service", {}):
            response = _object(ir["service"][key], f"$.service.{key}", ("type", "description"))
            type_ref(response["type"], f"$.service.{key}.type")
            if not isinstance(response["description"], str) or not response["description"]:
                raise ValueError(f"$.service.{key}.description: expected nonempty text")
    authenticated = "bearer_auth" in ir.get("service", {})
    if "unauthorized" in ir.get("service", {}) and not authenticated:
        raise ValueError("$.service.unauthorized: requires bearer_auth")

    operation_names = set()
    operation_ids = set()
    routes = {}
    for index, operation in enumerate(operations):
        location = f"$.operations[{index}]"
        operation = _object(
            operation, location,
            ("name", "cpp_name", "method", "path", "parameters", "returns", "result"),
            ("errors", "summary", "description", "response_description", "context_parameters",
             "public", "host_response", "success_status", "operation_id", "response_values",
             "response_format", "success_responses", "response_headers", "sse_events"),
        )
        if type(operation["result"]) is not bool:
            raise ValueError(f"{location}.result: expected boolean")
        host_served = "host_response" in operation
        if host_served:
            media_type = operation["host_response"]
            if not isinstance(media_type, str) or not MEDIA_TYPE.fullmatch(media_type):
                raise ValueError(f"{location}.host_response: expected a media type")
            if media_type != "application/json" and (
                operation["returns"] != {"kind": "builtin", "name": "string"}
            ):
                raise ValueError(f"{location}.host_response: a non-JSON response "
                                 "requires a string return")
            if operation.get("context_parameters"):
                raise ValueError(f"{location}: host-response operations have no context parameters")
        if "operation_id" in operation:
            _name(operation["operation_id"], f"{location}.operation_id")
            _unique(operation_ids, operation["operation_id"], location, "operation ID")
        returns_string = operation["returns"] == STRING
        for key in ("response_values", "response_format", "success_responses", "response_headers"):
            if key in operation and not host_served:
                raise ValueError(f"{location}.{key}: requires host_response")
        if "response_values" in operation:
            values = _array(operation["response_values"], f"{location}.response_values")
            if not returns_string or not values or any(
                not isinstance(value, str) or not value for value in values
            ) or len(set(values)) != len(values):
                raise ValueError(f"{location}.response_values: expected unique strings "
                                 "for a string response")
        if "response_format" in operation:
            if not returns_string or not isinstance(operation["response_format"], str) or (
                not FORMAT.fullmatch(operation["response_format"])
            ):
                raise ValueError(f"{location}.response_format: expected a format for a string response")
        if "sse_events" in operation and operation.get("host_response") != "text/event-stream":
            raise ValueError(f"{location}.sse_events: require a text/event-stream host response")
        event_names = set()
        for index, event in enumerate(_array(operation.get("sse_events", []), f"{location}.sse_events")):
            event_location = f"{location}.sse_events[{index}]"
            event = _object(event, event_location, ("name", "type"))
            if not isinstance(event["name"], str) or not event["name"]:
                raise ValueError(f"{event_location}.name: expected nonempty text")
            _unique(event_names, event["name"], event_location, "event")
            type_ref(event["type"], f"{event_location}.type")
        header_names = set()
        for index, header in enumerate(_array(operation.get("response_headers", []),
                                              f"{location}.response_headers")):
            header_location = f"{location}.response_headers[{index}]"
            header = _object(header, header_location, ("name", "description"))
            if not isinstance(header["name"], str) or not HEADER.fullmatch(header["name"]):
                raise ValueError(f"{header_location}.name: expected an HTTP header name")
            _unique(header_names, header["name"].lower(), header_location, "response header")
            if not isinstance(header["description"], str) or not header["description"]:
                raise ValueError(f"{header_location}.description: expected nonempty text")
        extra_statuses = set()
        for index, extra in enumerate(_array(operation.get("success_responses", []),
                                             f"{location}.success_responses")):
            extra_location = f"{location}.success_responses[{index}]"
            extra = _object(extra, extra_location, ("status", "description"))
            status = extra["status"]
            if type(status) is not int or not 200 <= status <= 299 or status in (204, 205) or (
                status == operation.get("success_status", 200)
            ):
                raise ValueError(f"{extra_location}.status: expected another 2xx status with a body")
            _unique(extra_statuses, status, extra_location, "success status")
            if not isinstance(extra["description"], str) or not extra["description"]:
                raise ValueError(f"{extra_location}.description: expected nonempty text")
        if "success_status" in operation:
            status = operation["success_status"]
            # Every success response has a body, which 204 and 205 cannot.
            if type(status) is not int or not 200 <= status <= 299 or status in (204, 205):
                raise ValueError(f"{location}.success_status: expected a 2xx status with a body")
        if "public" in operation:
            if operation["public"] is not True:
                raise ValueError(f"{location}.public: expected true")
            if not authenticated:
                raise ValueError(f"{location}.public: requires service bearer_auth")
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
        context_parameters = _array(operation.get("context_parameters", []),
                                    f"{location}.context_parameters")
        context_names = set()
        context_positions = set()
        for context_index, context in enumerate(context_parameters):
            context_location = f"{location}.context_parameters[{context_index}]"
            context = _object(context, context_location, ("name", "position"))
            context_name = _name(context["name"], f"{context_location}.name")
            _unique(context_names, context_name, location, "context parameter")
            position = context["position"]
            if type(position) is not int or not 0 <= position < len(parameters) + len(context_parameters):
                raise ValueError(f"{context_location}.position: invalid parameter position")
            _unique(context_positions, position, location, "context parameter position")
        parameter_names = set()
        by_name = {}
        for parameter_index, parameter in enumerate(parameters):
            parameter_location = f"{location}.parameters[{parameter_index}]"
            parameter = _object(parameter, parameter_location, ("name", "type"),
                                ("in", "range", "int_values", "description", "string_values",
                                 "minimum", "format", "min_length", "max_length", "default",
                                 "pattern", "header"))
            parameter_name = _name(parameter["name"], f"{parameter_location}.name")
            _unique(parameter_names, parameter_name, parameter_location, "parameter")
            if parameter_name in context_names:
                raise ValueError(f"{parameter_location}: also a context parameter")
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
            if "int_values" in parameter:
                values = _array(parameter["int_values"], f"{parameter_location}.int_values")
                if not 1 <= len(values) <= 16 or any(
                    type(value) is not int or not -(2 ** 31) <= value < 2 ** 31
                    for value in values
                ) or len(set(values)) != len(values):
                    raise ValueError(f"{parameter_location}.int_values: expected unique C++ integers")
                if query_value_type(parameter["type"]) != {"kind": "builtin", "name": "int"}:
                    raise ValueError(f"{parameter_location}.int_values: requires int or optional<int>")
                if "range" in parameter:
                    raise ValueError(f"{parameter_location}: range and int_values cannot be combined")
            if "description" in parameter and (
                not isinstance(parameter["description"], str) or not parameter["description"]
            ):
                raise ValueError(f"{parameter_location}.description: expected nonempty text")
            value_ref = query_value_type(parameter["type"])
            if "string_values" in parameter:
                choices = _array(parameter["string_values"], f"{parameter_location}.string_values")
                if not 1 <= len(choices) <= 16 or any(
                    not isinstance(choice, str) or not choice for choice in choices
                ) or len(set(choices)) != len(choices):
                    raise ValueError(f"{parameter_location}.string_values: expected unique nonempty strings")
                if value_ref != STRING:
                    raise ValueError(f"{parameter_location}.string_values: requires a string")
            if "minimum" in parameter:
                if type(parameter["minimum"]) is not int or value_ref != INTEGERS[0]:
                    raise ValueError(f"{parameter_location}.minimum: requires an int parameter")
                if "range" in parameter or "int_values" in parameter:
                    raise ValueError(f"{parameter_location}: minimum duplicates a range or int_values")
            _value_constraints(parameter, value_ref, parameter_location)
            if "default" in parameter and (
                parameter.get("in") != "query" or parameter["type"]["kind"] == "optional"
            ):
                raise ValueError(f"{parameter_location}.default: requires a query parameter "
                                 "whose type is not optional")
            if parameter.get("in") == "header":
                # Generated dispatch does not see request headers, so only the host reads them.
                if not isinstance(parameter.get("header"), str) or not HEADER.fullmatch(parameter["header"]):
                    raise ValueError(f"{parameter_location}.header: expected an HTTP header name")
                if query_value_type(parameter["type"]) != STRING:
                    raise ValueError(f"{parameter_location}: a header parameter is a string")
                if not host_served:
                    raise ValueError(f"{parameter_location}: header parameters require host_response")
            elif "header" in parameter:
                raise ValueError(f"{parameter_location}.header: requires in header")
            elif "in" in parameter:
                if parameter["in"] != "query":
                    raise ValueError(f"{parameter_location}.in: unsupported parameter location")
                query_ref = scalar(query_value_type(parameter["type"]))
                if query_ref["kind"] == "variant":
                    # A query value is text, so each alternative must decode from a string.
                    if any(scalar(alternative) != STRING for alternative in query_ref["alternatives"]):
                        raise ValueError(f"{parameter_location}: query variant alternatives must be strings")
                elif query_ref["kind"] != "builtin" or query_ref["name"] not in {
                    "int", "int64", "bool", "string"
                }:
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
            if parameter["name"] not in captures and parameter.get("in") not in ("query", "header")
        }
        if len(bodies) > 1:
            raise ValueError(f"{location}: operation {name} has multiple body parameters")
        if bodies and method == "GET":
            raise ValueError(f"{location}: operation {name} has a body with {method}")
        if any(parameter["name"] in bodies and "description" in parameter
               for parameter in parameters):
            raise ValueError(f"{location}: body parameter descriptions are unsupported")
        statuses = set()
        exceptions = set()
        for error_index, error in enumerate(_array(operation.get("errors", []), f"{location}.errors")):
            error_location = f"{location}.errors[{error_index}]"
            error = _object(error, error_location, ("status", "type"),
                            ("description", "exceptions"))
            if "exceptions" in error and "host_response" in operation:
                raise ValueError(f"{error_location}.exceptions: the host maps a host-response "
                                 f"operation's exceptions in {name}")
            if "exceptions" in error:
                mapped = _array(error["exceptions"], f"{error_location}.exceptions")
                if not mapped:
                    raise ValueError(f"{error_location}.exceptions: expected exception types")
                for exception_index, exception in enumerate(mapped):
                    exception_location = f"{error_location}.exceptions[{exception_index}]"
                    try:
                        exception = cpp_name(exception)
                    except ValueError as problem:
                        raise ValueError(f"{exception_location}: {problem}") from None
                    _unique(exceptions, exception, exception_location,
                            f"mapped exception in {name}")
            status = error["status"]
            if type(status) is not int or not 400 <= status <= 599:
                raise ValueError(f"{error_location}: invalid error status in {name}: {status!r}")
            _unique(statuses, status, error_location, f"response status in {name}")
            if status == 401 and "unauthorized" in ir.get("service", {}) and not operation.get("public"):
                raise ValueError(f"{error_location}: 401 is declared by the service in {name}")
            if "description" in error and (
                not isinstance(error["description"], str) or not error["description"]
            ):
                raise ValueError(f"{error_location}.description: expected nonempty text")
            type_ref(error["type"], f"{error_location}.type")
    return ir
