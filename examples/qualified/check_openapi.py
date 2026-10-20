import json
from pathlib import Path

ir = json.loads(Path("build/rig.json").read_text())
assert ir["ir_version"] == 12
assert {entry["cpp_name"] for entry in ir["types"]} == {
    "left::Result", "right::Result", "service::Pair"
}
assert {entry["cpp_name"] for entry in ir["operations"]} == {
    "left::read", "left::by_key", "left::newest", "left::limited", "left::query",
    "left::filter", "left::choices",
    "right::read",
    "service::echo", "service::check"
}
document = json.loads(Path("build/openapi.json").read_text())
schemas = document["components"]["schemas"]
assert set(schemas) == {"left.Result", "right.Result", "Pair", "RigInvalidRequest"}
assert schemas["Pair"]["properties"] == {
    "left": {"$ref": "#/components/schemas/left.Result"},
    "right": {"$ref": "#/components/schemas/right.Result"},
}
assert document["paths"]["/left"]["get"]["operationId"] == "left.read"
assert document["paths"]["/left/new"]["get"]["operationId"] == "newest"
assert document["paths"]["/right"]["get"]["operationId"] == "right.read"
assert document["paths"]["/left/limited"]["get"]["parameters"] == [{
    "name": "limit", "in": "query", "required": True, "schema": {"type": "integer"}
}]
assert document["paths"]["/left/query"]["get"]["parameters"] == [
    {"name": "text", "in": "query", "required": True, "schema": {"type": "string"}},
    {"name": "enabled", "in": "query", "required": True, "schema": {"type": "boolean"}},
]
assert document["paths"]["/left/filter"]["get"]["parameters"] == [
    {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer"}},
    {"name": "enabled", "in": "query", "required": False, "schema": {"type": "boolean"}},
    {"name": "text", "in": "query", "required": False, "schema": {"type": "string"}},
]
assert document["paths"]["/left/choices"]["get"]["parameters"] == [{
    "name": "selected", "in": "query", "required": False,
    "schema": {"type": "integer", "enum": [0, 1]},
    "description": "Choose zero or one",
}]
assert document["paths"]["/left/{key}"]["get"]["responses"]["400"]["content"]["application/json"]["schema"] == {
    "$ref": "#/components/schemas/RigInvalidRequest"
}
checked = document["paths"]["/checked"]["post"]["responses"]
assert checked["400"]["content"]["application/json"]["schema"] == {
    "$ref": "#/components/schemas/RigInvalidRequest"
}
assert checked["422"]["content"]["application/json"]["schema"] == {
    "$ref": "#/components/schemas/left.Result"
}
assert checked["503"]["content"]["application/json"]["schema"] == {
    "$ref": "#/components/schemas/right.Result"
}
