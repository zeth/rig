"""Translate RIG's small C++ declaration IR into OpenAPI 3.2 JSON."""

import copy
import json
import re

from .ir import public_names, query_value_type, request_needs_decoding, validate


PRIMITIVES = {
    "int": {"type": "integer"},
    "int64": {"type": "integer", "format": "int64"},
    "double": {"type": "number", "format": "double"},
    "bool": {"type": "boolean"},
    "string": {"type": "string"},
    "object": {"type": "object", "additionalProperties": True},
}


def convert(ir, title="API", version="0.1.0", include_operation_ids=True):
    validate(ir)
    service = ir.get("service")
    if service:
        title, version = service["title"], service["version"]
    types = {entry["cpp_name"]: entry for entry in ir["types"]}
    schema_names = public_names(types)
    operation_names = public_names(operation["cpp_name"] for operation in ir["operations"])
    inline_stack = set()

    def schema(type_ref):
        kind = type_ref["kind"]
        if kind == "builtin":
            name = type_ref["name"]
            if name in PRIMITIVES:
                return PRIMITIVES[name].copy()
            raise ValueError(f"unsupported builtin type: {name}")
        if kind == "named":
            name = type_ref["name"]
            if name in types:
                if types[name].get("inline"):
                    if name in inline_stack:
                        raise ValueError(f"recursive inline record: {name}")
                    inline_stack.add(name)
                    try:
                        return record_schema(types[name])
                    finally:
                        inline_stack.remove(name)
                return {"$ref": f"#/components/schemas/{schema_names[name]}"}
            raise ValueError(f"unregistered type: {name}")
        if kind == "array":
            return {"type": "array", "items": schema(type_ref["items"])}
        if kind == "variant":
            return {"oneOf": [schema(alternative) for alternative in type_ref["alternatives"]]}
        if kind == "map":
            return {"type": "object", "additionalProperties": schema(type_ref["values"])}
        if kind == "optional":
            # OpenAPI 3.1's idiom: a null type beside a typed schema, anyOf for a reference.
            inner = schema(type_ref["value"])
            if isinstance(inner.get("type"), str):
                inner["type"] = [inner["type"], "null"]
                return inner
            return {"anyOf": [inner, {"type": "null"}]}
        raise ValueError(f"unsupported type kind: {kind}")

    def add_constraints(result, item):
        """Add format, length, choice and default keywords to a value schema."""
        for key, keyword in (("format", "format"), ("pattern", "pattern"), ("min_length", "minLength"),
                             ("max_length", "maxLength"), ("default", "default")):
            if key in item:
                result[keyword] = item[key]
        return result

    def parameter_schema(parameter, query=False):
        ref = query_value_type(parameter["type"]) if query else parameter["type"]
        result = schema(ref)
        if "string_values" in parameter:
            result["enum"] = parameter["string_values"]
        if "minimum" in parameter:
            result["minimum"] = parameter["minimum"]
        add_constraints(result, parameter)
        if "range" in parameter:
            if ref["kind"] == "optional":
                result["anyOf"][0].update(parameter["range"])
            else:
                result.update(parameter["range"])
        if "int_values" in parameter:
            result["enum"] = parameter["int_values"]
        return result

    def record_schema(entry):
        properties = {}
        required = []
        for field in entry["fields"]:
            ref = field["type"]
            if field.get("omit_empty") or field.get("nullable"):
                ref = ref["value"]
            if field.get("omit_empty") and field.get("nullable"):
                ref = ref["value"]
            property_schema = schema(ref)
            if "bool_value" in field:
                property_schema["enum"] = [field["bool_value"]]
            if "string_values" in field:
                property_schema["enum"] = list(field["string_values"])
            if field.get("nullable"):
                if "type" in property_schema:
                    property_schema["type"] = [property_schema["type"], "null"]
                    if "enum" in property_schema:
                        property_schema["enum"].append(None)
                else:
                    property_schema = {"anyOf": [property_schema, {"type": "null"}]}
            if "description" in field and "$ref" in property_schema:
                property_schema = {"allOf": [property_schema]}
            for key in ("description", "minimum"):
                if key in field:
                    property_schema[key] = field[key]
            if field.get("write_only"):
                property_schema["writeOnly"] = True
            add_constraints(property_schema, field)
            properties[field["name"]] = property_schema
            if not field.get("omit_empty") and "default" not in field:
                required.append(field["name"])
        if entry.get("value"):
            # A value type is its one field on the wire.
            result = properties[entry["fields"][0]["name"]]
            if "description" in entry:
                result["description"] = entry["description"]
            return result
        result = {"type": "object", "properties": properties}
        if "min_properties" in entry:
            result["minProperties"] = entry["min_properties"]
        # An empty list means the same as none; OpenAPI documents usually omit it.
        if required:
            result["required"] = required
        if not entry.get("open", False):
            result["additionalProperties"] = False
        if "base" in entry:
            result = {"allOf": [schema({"kind": "named", "name": entry["base"]}), result]}
        if "description" in entry:
            result["description"] = entry["description"]
        return result

    components = {}
    for qualified, entry in types.items():
        name = schema_names[qualified]
        if entry["kind"] == "record":
            if not entry.get("inline"):
                components[name] = record_schema(entry)
        elif entry["kind"] == "enum":
            components[name] = {"type": "string", "enum": entry["values"]}
        else:
            raise ValueError(f"unsupported declaration kind: {entry['kind']}")

    validation = service.get("validation_error") if service else None
    invalid_request_name = "RigInvalidRequest"
    if not validation and any(request_needs_decoding(operation) for operation in ir["operations"]):
        suffix = 2
        while invalid_request_name in components:
            invalid_request_name = f"RigInvalidRequest{suffix}"
            suffix += 1
        components[invalid_request_name] = {
            "type": "object",
            "properties": {
                "code": {"type": "string", "enum": ["invalid_request"]},
                "message": {"type": "string"},
            },
            "required": ["code", "message"],
            "additionalProperties": False,
        }

    def add_generated_response(result, status, body_schema, description):
        """Add a response the generated dispatcher can return, keeping a declared one."""
        existing = result["responses"].get(status)
        if not existing:
            result["responses"][status] = {
                "description": description,
                "content": {"application/json": {"schema": body_schema}},
            }
            return
        declared = existing["content"]["application/json"]["schema"]
        if declared != body_schema:
            existing["content"]["application/json"]["schema"] = {
                "anyOf": [declared, body_schema],
            }

    paths = {}
    for operation in ir["operations"]:
        method = operation["method"].lower()
        path = operation["path"]
        placeholders = set(re.findall(r"\{([^{}]+)\}", path))
        parameters = []
        bodies = []
        for parameter in operation["parameters"]:
            name = parameter["name"]
            if name in placeholders:
                item = {
                    "name": name,
                    "in": "path",
                    "required": True,
                    "schema": parameter_schema(parameter),
                }
                if "description" in parameter:
                    item["description"] = parameter["description"]
                parameters.append(item)
                placeholders.remove(name)
            elif parameter.get("in") == "query":
                item = {
                    "name": name,
                    "in": "query",
                    "required": parameter["type"]["kind"] != "optional" and "default" not in parameter,
                    "schema": parameter_schema(parameter, query=True),
                }
                if "description" in parameter:
                    item["description"] = parameter["description"]
                parameters.append(item)
            elif parameter.get("in") == "header":
                item = {"name": parameter["header"], "in": "header",
                        "schema": parameter_schema(parameter, query=True)}
                # A header is optional unless required, so only a required one says so.
                if parameter["type"]["kind"] != "optional":
                    item["required"] = True
                if "description" in parameter:
                    item["description"] = parameter["description"]
                parameters.append(item)
            else:
                bodies.append(parameter)

        result = {}
        if "operation_id" in operation:
            result["operationId"] = operation["operation_id"]
        elif include_operation_ids:
            result["operationId"] = operation_names[operation["cpp_name"]]
        media_type = operation.get("host_response", "application/json")
        if media_type == EVENT_STREAM:
            success_media = {"itemSchema": event_schema(operation.get("sse_events", []), schema)}
        elif operation.get("response_format") == "binary":
            # Raw bytes: a binary media type needs no schema.
            success_media = {}
        else:
            success_schema = schema(operation["returns"])
            if "response_values" in operation:
                success_schema["enum"] = operation["response_values"]
            if "response_format" in operation:
                success_schema["format"] = operation["response_format"]
            success_media = {"schema": success_schema}
        result["responses"] = {
            str(operation.get("success_status", 200)): {
                "description": operation.get("response_description", "Success"),
                "content": {media_type: success_media}
            }
        }
        if "response_headers" in operation:
            headers = {header["name"]: {"description": header["description"],
                                        "schema": {"type": "string"}}
                       for header in operation["response_headers"]}
            for response in result["responses"].values():
                response["headers"] = headers
        for extra in operation.get("success_responses", []):
            # A 204 has no content: for an event stream, it tells a reconnecting client the stream
            # is finished.
            result["responses"][str(extra["status"])] = (
                {"description": extra["description"]} if extra["status"] == 204 else {
                    "description": extra["description"],
                    "content": {media_type: copy.deepcopy(success_media)},
                })
        for key in ("summary", "description"):
            if key in operation:
                result[key] = operation[key]
        for error in operation.get("errors", []):
            status = error["status"]
            key = str(status)
            result["responses"][key] = {
                "description": error.get("description", "Error"),
                "content": {"application/json": {"schema": schema(error["type"])}}
            }
        unauthorized = service.get("unauthorized") if service else None
        if operation.get("public"):
            result["security"] = []
        elif unauthorized:
            result["responses"]["401"] = {
                "description": unauthorized["description"],
                "content": {"application/json": {"schema": schema(unauthorized["type"])}}
            }
        if request_needs_decoding(operation):
            if validation:
                add_generated_response(result, "400", schema(validation["type"]),
                                       validation["description"])
            else:
                add_generated_response(
                    result, "400",
                    {"$ref": f"#/components/schemas/{invalid_request_name}"},
                    "Invalid request",
                )
        # The generated dispatcher's catch never sees a host-response operation.
        internal = service.get("internal_error") if service else None
        if internal and "host_response" not in operation:
            add_generated_response(result, "500", schema(internal["type"]),
                                   internal["description"])
        if parameters:
            result["parameters"] = parameters
        if bodies:
            body = bodies[0]
            optional_body = body["type"]["kind"] == "optional"
            body_schema = schema(body["type"]["value"]) if optional_body else parameter_schema(body)
            result["requestBody"] = {
                "required": not optional_body,
                "content": {"application/json": {"schema": body_schema}}
            }
        methods = paths.setdefault(path, {})
        methods[method] = result

    document = {
        "openapi": "3.2.0",
        "info": {"title": title, "version": version},
        "paths": paths,
        "components": {"schemas": components},
    }
    if service:
        document["servers"] = [{"url": url} for url in service["servers"]]
        if "bearer_auth" in service:
            name = service["bearer_auth"]["name"]
            document["components"]["securitySchemes"] = {
                name: {
                    "type": "http", "scheme": "bearer",
                    "bearerFormat": service["bearer_auth"]["format"],
                }
            }
            document["security"] = [{name: []}]
    return ordered(document)


EVENT_STREAM = "text/event-stream"


def event_schema(events, schema):
    """An event stream's itemSchema: the fields of one event, as OpenAPI 3.2 models them.

    Each declared event is one alternative that fixes its name and gives its JSON data's schema.
    Without declared events, any event matches."""
    def event(name=None, data_schema=None):
        data = {"type": "string"}
        if data_schema is not None:
            data.update(contentMediaType="application/json", contentSchema=data_schema)
        return {
            "type": "object",
            "properties": {
                "event": {"type": "string"} if name is None else {"const": name},
                "data": data,
                "id": {"type": "string"},
                "retry": {"type": "integer", "minimum": 0},
            },
            "required": ["data"] if name is None else ["event", "data"],
        }
    if not events:
        return event()
    return {"oneOf": [event(item["name"], schema(item["type"])) for item in events]}


METHOD_ORDER = ("get", "put", "post", "patch", "delete")
OPERATION_ORDER = ("operationId", "summary", "description", "security", "parameters",
                   "requestBody", "responses")


def _in_order(mapping, order):
    """The mapping with known keys in the given order, then any others."""
    keys = [key for key in order if key in mapping] + [key for key in mapping if key not in order]
    return {key: mapping[key] for key in keys}


def ordered(document):
    """Order a document so it does not depend on where declarations live.

    Paths and schemas are sorted by name, methods and operation keys follow
    OpenAPI's usual order, and responses are sorted by status.
    """
    paths = {}
    for path in sorted(document["paths"]):
        methods = _in_order(document["paths"][path], METHOD_ORDER)
        paths[path] = {}
        for method, operation in methods.items():
            operation = _in_order(operation, OPERATION_ORDER)
            operation["responses"] = dict(sorted(operation["responses"].items()))
            paths[path][method] = operation
    components = {key: document["components"][key]
                  for key in ("securitySchemes", "schemas") if key in document["components"]}
    components["schemas"] = dict(sorted(components["schemas"].items()))
    result = _in_order(document, ("openapi", "info", "servers", "security", "paths", "components"))
    result["paths"] = paths
    result["components"] = components
    return result


def dumps(document, output_format="json"):
    """Serialize a document as JSON or YAML, with a final newline."""
    if output_format == "json":
        return json.dumps(document, indent=2) + "\n"
    import yaml  # Only YAML output needs PyYAML.
    # Lists and maps of plain values stay on one line, as hand-written OpenAPI usually has them.
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=100,
                          default_flow_style=None)
