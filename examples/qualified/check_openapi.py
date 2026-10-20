import json
from pathlib import Path

ir = json.loads(Path("build/rig.json").read_text())
assert ir["ir_version"] == 3
assert {entry["cpp_name"] for entry in ir["types"]} == {
    "left::Result", "right::Result", "service::Pair"
}
assert {entry["cpp_name"] for entry in ir["operations"]} == {
    "left::read", "right::read", "service::echo"
}
document = json.loads(Path("build/openapi.json").read_text())
schemas = document["components"]["schemas"]
assert set(schemas) == {"left.Result", "right.Result", "Pair"}
assert schemas["Pair"]["properties"] == {
    "left": {"$ref": "#/components/schemas/left.Result"},
    "right": {"$ref": "#/components/schemas/right.Result"},
}
assert document["paths"]["/left"]["get"]["operationId"] == "left.read"
assert document["paths"]["/right"]["get"]["operationId"] == "right.read"
