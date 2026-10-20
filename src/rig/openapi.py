"""Translate RIG's small C++ declaration IR into OpenAPI 3.1 JSON."""

import re

from .ir import validate


PRIMITIVES = {
    "int": {"type": "integer"},
    "bool": {"type": "boolean"},
    "string": {"type": "string"},
}


def convert(ir, title="API", version="0.1.0"):
    validate(ir)
    types = {entry["name"]: entry for entry in ir["types"]}

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
                return {"$ref": f"#/components/schemas/{name}"}
            raise ValueError(f"unregistered type: {name}")
        if kind == "array":
            return {"type": "array", "items": schema(type_ref["items"])}
        if kind == "optional":
            return {"anyOf": [schema(type_ref["value"]), {"type": "null"}]}
        raise ValueError(f"unsupported type kind: {kind}")

    components = {}
    for name, entry in types.items():
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
            else:
                bodies.append(parameter)

        result = {
            "operationId": operation["name"],
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
