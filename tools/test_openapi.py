import unittest

from openapi import convert


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.ir = {
            "ir_version": 2,
            "types": [{
                "kind": "record", "name": "Result", "fields": [
                    {"name": "ok", "type": {"kind": "builtin", "name": "bool"}}
                ]
            }],
            "operations": [{
                "name": "get_result",
                "method": "GET",
                "path": "/results/{id}",
                "parameters": [{"name": "id", "type": {"kind": "builtin", "name": "int"}}],
                "returns": {"kind": "named", "name": "Result"},
            }],
        }

    def test_path_and_record_are_connected(self):
        document = convert(self.ir)
        operation = document["paths"]["/results/{id}"]["get"]
        self.assertEqual(operation["parameters"][0]["in"], "path")
        self.assertEqual(
            operation["responses"]["200"]["content"]["application/json"]["schema"],
            {"$ref": "#/components/schemas/Result"},
        )

    def test_unbound_path_is_rejected(self):
        self.ir["operations"][0]["parameters"] = []
        with self.assertRaisesRegex(ValueError, "unbound placeholders"):
            convert(self.ir)

    def test_unknown_type_is_rejected(self):
        self.ir["types"][0]["fields"][0]["type"] = {
            "kind": "named", "name": "Mystery"
        }
        with self.assertRaisesRegex(ValueError, "unregistered type"):
            convert(self.ir)

    def test_enum_array_and_optional(self):
        self.ir["types"].append({
            "kind": "enum", "name": "Winner", "values": ["Human", "Bot"]
        })
        self.ir["types"][0]["fields"].extend([
            {"name": "history", "type": {
                "kind": "array", "items": {"kind": "named", "name": "Winner"}
            }},
            {"name": "winner", "type": {
                "kind": "optional", "value": {"kind": "named", "name": "Winner"}
            }},
        ])
        schemas = convert(self.ir)["components"]["schemas"]
        self.assertEqual(schemas["Winner"], {"type": "string", "enum": ["Human", "Bot"]})
        self.assertEqual(
            schemas["Result"]["properties"]["history"],
            {"type": "array", "items": {"$ref": "#/components/schemas/Winner"}},
        )
        self.assertEqual(
            schemas["Result"]["properties"]["winner"],
            {"anyOf": [{"$ref": "#/components/schemas/Winner"}, {"type": "null"}]},
        )


if __name__ == "__main__":
    unittest.main()
