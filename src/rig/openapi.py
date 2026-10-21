"""Translate RIG's small C++ declaration IR into OpenAPI 3.1 JSON."""

import re

from .ir import public_names, query_value_type, request_needs_decoding, validate


PRIMITIVES = {
    "int": {"type": "integer"},
    "int64": {"type": "integer", "format": "int64"},
    "double": {"type": "number", "format": "double"},
    "bool": {"type": "boolean"},
    "string": {"type": "string"},
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
        if kind == "optional":
            return {"anyOf": [schema(type_ref["value"]), {"type": "null"}]}
        raise ValueError(f"unsupported type kind: {kind}")

    def parameter_schema(parameter, query=False):
        ref = query_value_type(parameter["type"]) if query else parameter["type"]
        result = schema(ref)
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
            if field.get("nullable"):
                property_schema["type"] = [property_schema["type"], "null"]
            if "bool_value" in field:
                property_schema["enum"] = [field["bool_value"]]
            if "string_values" in field:
                property_schema["enum"] = field["string_values"]
            if "description" in field and "$ref" in property_schema:
                property_schema = {"allOf": [property_schema]}
            for key in ("description", "minimum"):
                if key in field:
                    property_schema[key] = field[key]
            properties[field["name"]] = property_schema
            if not field.get("omit_empty"):
                required.append(field["name"])
        result = {
            "type": "object",
            "properties": properties,
            "required": required,
        }
        if not entry.get("open", False):
            result["additionalProperties"] = False
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
                    "required": parameter["type"]["kind"] != "optional",
                    "schema": parameter_schema(parameter, query=True),
                }
                if "description" in parameter:
                    item["description"] = parameter["description"]
                parameters.append(item)
            else:
                bodies.append(parameter)

        result = {}
        if include_operation_ids:
            result["operationId"] = operation_names[operation["cpp_name"]]
        media_type = operation.get("host_response", "application/json")
        result["responses"] = {
            "200": {
                "description": operation.get("response_description", "Success"),
                "content": {media_type: {"schema": schema(operation["returns"])}}
            }
        }
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
            result["requestBody"] = {
                "required": True,
                "content": {"application/json": {"schema": parameter_schema(bodies[0])}}
            }
        methods = paths.setdefault(path, {})
        methods[method] = result

    document = {
        "openapi": "3.1.0",
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
    return document
