import unittest

from rig.openapi import convert


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.ir = {
            "ir_version": 3,
            "types": [{
                "kind": "record", "name": "Result", "cpp_name": "sample::Result", "fields": [
                    {"name": "ok", "type": {"kind": "builtin", "name": "bool"}}
                ]
            }],
            "operations": [{
                "name": "get_result", "cpp_name": "sample::get_result",
                "method": "GET",
                "path": "/results/{id}",
                "parameters": [{"name": "id", "type": {"kind": "builtin", "name": "int"}}],
                "returns": {"kind": "named", "name": "sample::Result"},
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

    def test_typed_error_response(self):
        self.ir["types"].append({
            "kind": "record", "name": "ErrorResponse", "cpp_name": "sample::ErrorResponse", "fields": [
                {"name": "error", "type": {"kind": "builtin", "name": "string"}}
            ]
        })
        self.ir["operations"][0]["errors"] = [
            {"status": 404, "type": {"kind": "named", "name": "sample::ErrorResponse"}}
        ]
        responses = convert(self.ir)["paths"]["/results/{id}"]["get"]["responses"]
        self.assertEqual(
            responses["404"]["content"]["application/json"]["schema"],
            {"$ref": "#/components/schemas/ErrorResponse"},
        )

    def test_invalid_error_status_is_rejected(self):
        self.ir["operations"][0]["errors"] = [
            {"status": 200, "type": {"kind": "named", "name": "sample::Result"}}
        ]
        with self.assertRaisesRegex(ValueError, "invalid error status"):
            convert(self.ir)

    def test_duplicate_error_status_is_rejected(self):
        self.ir["operations"][0]["errors"] = [
            {"status": 404, "type": {"kind": "named", "name": "sample::Result"}},
            {"status": 404, "type": {"kind": "named", "name": "sample::Result"}},
        ]
        with self.assertRaisesRegex(ValueError, "duplicate response status"):
            convert(self.ir)

    def test_enum_array_and_optional(self):
        self.ir["types"].append({
            "kind": "enum", "name": "Winner", "cpp_name": "sample::Winner", "values": ["Human", "Bot"]
        })
        self.ir["types"][0]["fields"].extend([
            {"name": "history", "type": {
                "kind": "array", "items": {"kind": "named", "name": "sample::Winner"}
            }},
            {"name": "winner", "type": {
                "kind": "optional", "value": {"kind": "named", "name": "sample::Winner"}
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
