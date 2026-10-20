#!/usr/bin/env python3
"""Translate RIG's small C++ declaration IR into OpenAPI 3.1 JSON."""

import argparse
import json
import re
import sys


PRIMITIVES = {
    "int": {"type": "integer"},
    "bool": {"type": "boolean"},
    "string": {"type": "string"},
}


def convert(ir, title="API", version="0.1.0"):
    if ir.get("ir_version") != 2:
        raise ValueError("unsupported RIG IR version")

    types = {entry["name"]: entry for entry in ir["types"]}
    if len(types) != len(ir["types"]):
        raise ValueError("duplicate type name")

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
            if len(properties) != len(entry["fields"]):
                raise ValueError(f"duplicate field in {name}")
            components[name] = {
                "type": "object",
                "properties": properties,
                "required": list(properties),
                "additionalProperties": False,
            }
        elif entry["kind"] == "enum":
            if len(set(entry["values"])) != len(entry["values"]):
                raise ValueError(f"duplicate enum value in {name}")
            components[name] = {"type": "string", "enum": entry["values"]}
        else:
            raise ValueError(f"unsupported declaration kind: {entry['kind']}")

    paths = {}
    for operation in ir["operations"]:
        method = operation["method"].lower()
        if method not in {"get", "post", "put", "patch", "delete"}:
            raise ValueError(f"unsupported HTTP method: {method}")
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
        if placeholders:
            raise ValueError(f"route {path} has unbound placeholders: {sorted(placeholders)}")
        if len(bodies) > 1:
            raise ValueError(f"operation {operation['name']} has multiple body parameters")
        if bodies and method in {"get", "delete"}:
            raise ValueError(f"operation {operation['name']} has a body with {method.upper()}")

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
            if type(status) is not int or not 400 <= status <= 599:
                raise ValueError(f"invalid error status in {operation['name']}: {status}")
            key = str(status)
            if key in result["responses"]:
                raise ValueError(f"duplicate response status in {operation['name']}: {status}")
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
        if method in methods:
            raise ValueError(f"duplicate route: {method.upper()} {path}")
        methods[method] = result

    return {
        "openapi": "3.1.0",
        "info": {"title": title, "version": version},
        "paths": paths,
        "components": {"schemas": components},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", default="API")
    parser.add_argument("--version", default="0.1.0")
    args = parser.parse_args()
    try:
        document = convert(json.load(sys.stdin), args.title, args.version)
        json.dump(document, sys.stdout, indent=2)
        sys.stdout.write("\n")
    except (KeyError, ValueError) as error:
        print(f"RIG OpenAPI generation failed: {error}", file=sys.stderr)
        sys.exit(1)
