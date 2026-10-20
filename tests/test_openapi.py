import unittest

from rig.http_routes import generate as generate_routes
from rig.openapi import convert


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.ir = {
            "ir_version": 11,
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

    def test_reflected_documentation_and_boolean_value(self):
        self.ir["types"][0]["fields"][0]["bool_value"] = True
        self.ir["operations"][0].update(
            summary="Leaving", description="A hint to the server.",
            response_description="Acknowledged",
        )
        document = convert(self.ir)
        self.assertEqual(document["components"]["schemas"]["Result"]["properties"]["ok"],
                         {"type": "boolean", "enum": [True]})
        operation = document["paths"]["/results/{id}"]["get"]
        self.assertEqual(operation["summary"], "Leaving")
        self.assertEqual(operation["description"], "A hint to the server.")
        self.assertEqual(operation["responses"]["200"]["description"], "Acknowledged")

    def test_field_description_and_minimum(self):
        self.ir["types"][0]["fields"].append({
            "name": "count", "type": {"kind": "builtin", "name": "int"},
            "minimum": 1, "description": "Live items.",
        })
        self.assertEqual(
            convert(self.ir)["components"]["schemas"]["Result"]["properties"]["count"],
            {"type": "integer", "minimum": 1, "description": "Live items."},
        )

    def test_external_context_is_not_an_http_parameter_or_generated_400(self):
        self.ir["operations"][0]["context_parameters"] = ["database"]
        document = convert(self.ir)
        operation = document["paths"]["/results/{id}"]["get"]
        self.assertEqual([item["name"] for item in operation["parameters"]], ["id"])
        self.assertNotIn("400", operation["responses"])
        with self.assertRaisesRegex(ValueError, "cannot supply context parameters"):
            generate_routes(self.ir, "codec.hpp")

    def test_omittable_nullable_and_numeric_fields(self):
        self.ir["types"][0]["fields"].extend([
            {"name": "updated_at", "type": {"kind": "builtin", "name": "int64"}},
            {"name": "percent", "type": {"kind": "builtin", "name": "double"}},
            {"name": "label", "type": {"kind": "optional", "value": {
                "kind": "builtin", "name": "string"}}, "omit_empty": True},
            {"name": "error", "type": {"kind": "optional", "value": {
                "kind": "builtin", "name": "string"}}, "nullable": True},
            {"name": "maybe_error", "type": {"kind": "optional", "value": {
                "kind": "optional", "value": {"kind": "builtin", "name": "string"}}},
             "omit_empty": True, "nullable": True},
        ])
        result = convert(self.ir)["components"]["schemas"]["Result"]
        self.assertEqual(result["required"], ["ok", "updated_at", "percent", "error"])
        self.assertEqual(result["properties"]["updated_at"],
                         {"type": "integer", "format": "int64"})
        self.assertEqual(result["properties"]["percent"],
                         {"type": "number", "format": "double"})
        self.assertEqual(result["properties"]["label"], {"type": "string"})
        self.assertEqual(result["properties"]["error"], {"type": ["string", "null"]})
        self.assertEqual(result["properties"]["maybe_error"],
                         {"type": ["string", "null"]})

    def test_open_record_and_omitted_operation_id(self):
        self.ir["types"][0]["open"] = True
        document = convert(self.ir, include_operation_ids=False)
        self.assertNotIn("additionalProperties", document["components"]["schemas"]["Result"])
        self.assertNotIn("operationId", document["paths"]["/results/{id}"]["get"])

    def test_service_metadata_and_bearer_security(self):
        self.ir["service"] = {
            "title": "Example API", "version": "0.2.0",
            "servers": ["/", "http://127.0.0.1:9000"],
            "bearer_auth": {"name": "bearerAuth", "format": "token"},
        }
        document = convert(self.ir)
        self.assertEqual(document["info"], {"title": "Example API", "version": "0.2.0"})
        self.assertEqual(document["servers"], [
            {"url": "/"}, {"url": "http://127.0.0.1:9000"},
        ])
        self.assertEqual(document["security"], [{"bearerAuth": []}])
        self.assertEqual(document["components"]["securitySchemes"], {
            "bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "token"},
        })

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

    def test_optional_query_parameter_is_not_required_or_nullable(self):
        self.ir["operations"][0]["path"] = "/results"
        self.ir["operations"][0]["parameters"] = [{
            "name": "limit", "in": "query",
            "type": {"kind": "optional", "value": {"kind": "builtin", "name": "int"}},
        }]
        operation = convert(self.ir)["paths"]["/results"]["get"]
        self.assertEqual(operation["parameters"], [{
            "name": "limit", "in": "query", "required": False,
            "schema": {"type": "integer"},
        }])
        self.assertIn("400", operation["responses"])

    def test_range_on_path_and_optional_query(self):
        operation = self.ir["operations"][0]
        operation["parameters"][0]["range"] = {"minimum": 1, "maximum": 20}
        operation["parameters"].append({
            "name": "limit", "in": "query",
            "type": {"kind": "optional", "value": {"kind": "builtin", "name": "int"}},
            "range": {"minimum": 2, "maximum": 10},
        })
        parameters = convert(self.ir)["paths"]["/results/{id}"]["get"]["parameters"]
        self.assertEqual(parameters[0]["schema"],
                         {"type": "integer", "minimum": 1, "maximum": 20})
        self.assertEqual(parameters[1]["schema"],
                         {"type": "integer", "minimum": 2, "maximum": 10})

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
            {"status": 404, "type": {"kind": "named", "name": "sample::ErrorResponse"},
             "description": "Not found"}
        ]
        responses = convert(self.ir)["paths"]["/results/{id}"]["get"]["responses"]
        self.assertEqual(
            responses["404"]["content"]["application/json"]["schema"],
            {"$ref": "#/components/schemas/ErrorResponse"},
        )
        self.assertEqual(responses["404"]["description"], "Not found")

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
