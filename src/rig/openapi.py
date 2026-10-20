"""Translate RIG's small C++ declaration IR into OpenAPI 3.1 JSON."""

import re

from .ir import public_names, request_needs_decoding, validate


PRIMITIVES = {
    "int": {"type": "integer"},
    "bool": {"type": "boolean"},
    "string": {"type": "string"},
}


def convert(ir, title="API", version="0.1.0"):
    validate(ir)
    types = {entry["cpp_name"]: entry for entry in ir["types"]}
    schema_names = public_names(types)
    operation_names = public_names(operation["cpp_name"] for operation in ir["operations"])

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
                return {"$ref": f"#/components/schemas/{schema_names[name]}"}
            raise ValueError(f"unregistered type: {name}")
        if kind == "array":
            return {"type": "array", "items": schema(type_ref["items"])}
        if kind == "optional":
            return {"anyOf": [schema(type_ref["value"]), {"type": "null"}]}
        raise ValueError(f"unsupported type kind: {kind}")

    components = {}
    for qualified, entry in types.items():
        name = schema_names[qualified]
        if entry["kind"] == "record":
            properties = {field["name"]: schema(field["type"]) for field in entry["fields"]}
            components[name] = {
                "type": "object",
                "properties": properties,
                "required": list(properties),
                "additionalProperties": False,
            }
        elif entry["kind"] == "enum":
            components[name] = {"type": "string", "enum": entry["values"]}
        else:
            raise ValueError(f"unsupported declaration kind: {entry['kind']}")

    invalid_request_name = "RigInvalidRequest"
    if any(request_needs_decoding(operation) for operation in ir["operations"]):
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
                parameters.append({
                    "name": name,
                    "in": "path",
                    "required": True,
                    "schema": schema(parameter["type"]),
                })
                placeholders.remove(name)
            elif parameter.get("in") == "query":
                parameters.append({
                    "name": name,
                    "in": "query",
                    "required": True,
                    "schema": schema(parameter["type"]),
                })
            else:
                bodies.append(parameter)

        result = {
            "operationId": operation_names[operation["cpp_name"]],
            "responses": {
                "200": {
                    "description": "Success",
                    "content": {"application/json": {"schema": schema(operation["returns"])}}
                }
            },
        }
        for error in operation.get("errors", []):
            status = error["status"]
            key = str(status)
            result["responses"][key] = {
                "description": "Error",
                "content": {"application/json": {"schema": schema(error["type"])}}
            }
        if request_needs_decoding(operation):
            invalid_schema = {"$ref": f"#/components/schemas/{invalid_request_name}"}
            existing = result["responses"].get("400")
            if existing:
                error_schema = existing["content"]["application/json"]["schema"]
                existing["content"]["application/json"]["schema"] = {
                    "anyOf": [error_schema, invalid_schema],
                }
            else:
                result["responses"]["400"] = {
                    "description": "Invalid request",
                    "content": {"application/json": {"schema": invalid_schema}},
                }
        if parameters:
            result["parameters"] = parameters
        if bodies:
            result["requestBody"] = {
                "required": True,
                "content": {"application/json": {"schema": schema(bodies[0]["type"])}}
            }
        methods = paths.setdefault(path, {})
        methods[method] = result

    return {
        "openapi": "3.1.0",
        "info": {"title": title, "version": version},
        "paths": paths,
        "components": {"schemas": components},
    }
