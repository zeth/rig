import unittest

from rig.openapi import convert


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.ir = {
            "ir_version": 4,
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

    def test_integer_path_advertises_generated_invalid_request(self):
        document = convert(self.ir)
        invalid = document["components"]["schemas"]["RigInvalidRequest"]
        self.assertEqual(invalid["required"], ["code", "message"])
        self.assertEqual(invalid["properties"]["code"]["enum"], ["invalid_request"])
        response = document["paths"]["/results/{id}"]["get"]["responses"]["400"]
        self.assertEqual(response["content"]["application/json"]["schema"], {
            "$ref": "#/components/schemas/RigInvalidRequest",
        })

    def test_string_path_advertises_invalid_percent_escape(self):
        self.ir["operations"][0]["path"] = "/results/{key}"
        self.ir["operations"][0]["parameters"] = [
            {"name": "key", "type": {"kind": "builtin", "name": "string"}}
        ]
        response = convert(self.ir)["paths"]["/results/{key}"]["get"]["responses"]["400"]
        self.assertEqual(response["content"]["application/json"]["schema"], {
            "$ref": "#/components/schemas/RigInvalidRequest",
        })

    def test_query_parameter_is_required_and_advertises_invalid_request(self):
        self.ir["operations"][0]["path"] = "/results"
        self.ir["operations"][0]["parameters"] = [
            {"name": "limit", "type": {"kind": "builtin", "name": "int"}, "in": "query"}
        ]
        operation = convert(self.ir)["paths"]["/results"]["get"]
        self.assertEqual(operation["parameters"], [{
            "name": "limit", "in": "query", "required": True,
            "schema": {"type": "integer"},
        }])
        self.assertIn("400", operation["responses"])
        self.assertNotIn("requestBody", operation)

    def test_declared_400_and_generated_invalid_request_share_response(self):
        self.ir["operations"][0]["errors"] = [{
            "status": 400, "type": {"kind": "named", "name": "sample::Result"},
        }]
        document = convert(self.ir)
        response = document["paths"]["/results/{id}"]["get"]["responses"]["400"]
        self.assertEqual(response["content"]["application/json"]["schema"], {
            "anyOf": [
                {"$ref": "#/components/schemas/Result"},
                {"$ref": "#/components/schemas/RigInvalidRequest"},
            ],
        })

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
