import json
import unittest

from rig.http_routes import generate as generate_routes
from rig.openapi import convert, dumps


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.ir = {
            "ir_version": 12,
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
                "result": False,
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

    def test_string_choices_and_described_reference(self):
        self.ir["types"].append({
            "kind": "record", "name": "Detail", "cpp_name": "sample::Detail",
            "fields": [{"name": "name", "type": {"kind": "builtin", "name": "string"}}],
        })
        self.ir["types"][0]["fields"].extend([
            {"name": "status", "type": {"kind": "builtin", "name": "string"},
             "string_values": ["live", "trashed"]},
            {"name": "detail", "type": {"kind": "optional", "value": {
                "kind": "named", "name": "sample::Detail"}}, "omit_empty": True,
             "description": "Present when resolved."},
        ])
        properties = convert(self.ir)["components"]["schemas"]["Result"]["properties"]
        self.assertEqual(properties["status"],
                         {"type": "string", "enum": ["live", "trashed"]})
        self.assertEqual(properties["detail"], {
            "allOf": [{"$ref": "#/components/schemas/Detail"}],
            "description": "Present when resolved.",
        })

    def test_inline_record_appears_at_use_site(self):
        self.ir["types"].append({
            "kind": "record", "name": "Detail", "cpp_name": "sample::Detail",
            "open": True, "inline": True,
            "fields": [{"name": "name", "type": {"kind": "builtin", "name": "string"}}],
        })
        self.ir["types"][0]["fields"].append({
            "name": "detail", "type": {"kind": "named", "name": "sample::Detail"},
        })
        document = convert(self.ir)
        self.assertNotIn("Detail", document["components"]["schemas"])
        self.assertEqual(document["components"]["schemas"]["Result"]["properties"]["detail"], {
            "type": "object", "required": ["name"], "properties": {"name": {"type": "string"}},
        })

    def test_configured_validation_error_documents_each_decoded_operation(self):
        error_ref = {"kind": "named", "name": "sample::Result"}
        self.ir["service"] = {"title": "Sample", "version": "1.0", "servers": [],
                              "validation_error": {"type": error_ref, "description": "Bad request"}}
        self.ir["operations"].append({
            "name": "set_result", "cpp_name": "sample::set_result", "method": "PUT",
            "path": "/results/{id}/state",
            "parameters": [{"name": "id", "type": {"kind": "builtin", "name": "int"}}],
            "returns": error_ref, "result": False,
            "errors": [{"status": 400, "type": error_ref, "description": "Rejected"}],
        })
        self.ir["operations"].append({
            "name": "list_results", "cpp_name": "sample::list_results", "method": "GET",
            "path": "/results", "parameters": [], "returns": error_ref, "result": False,
        })
        document = convert(self.ir)
        self.assertNotIn("RigInvalidRequest", document["components"]["schemas"])
        self.assertEqual(document["paths"]["/results/{id}"]["get"]["responses"]["400"], {
            "description": "Bad request",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Result"}}},
        })
        # A declared 400 with the same body is already the validation response.
        self.assertEqual(
            document["paths"]["/results/{id}/state"]["put"]["responses"]["400"]["description"],
            "Rejected",
        )
        self.assertNotIn("400", document["paths"]["/results"]["get"]["responses"])
        routes = generate_routes(self.ir, "codec.hpp")
        self.assertIn("return {400, encode_error<sample::Result>(400, error), operation};", routes)
        self.assertNotIn('"invalid_request"', routes)

    def test_service_unauthorized_response_skips_public_operations(self):
        result = {"kind": "named", "name": "sample::Result"}
        self.ir["service"] = {"title": "Sample", "version": "1.0", "servers": [],
                              "bearer_auth": {"name": "bearerAuth", "format": "token"},
                              "unauthorized": {"type": result, "description": "Unauthorized"}}
        self.ir["operations"].append({
            "name": "ping", "cpp_name": "sample::ping", "method": "GET", "path": "/ping",
            "parameters": [], "returns": result, "result": False, "public": True,
        })
        document = convert(self.ir)
        authenticated = document["paths"]["/results/{id}"]["get"]
        self.assertEqual(authenticated["responses"]["401"], {
            "description": "Unauthorized",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Result"}}},
        })
        self.assertNotIn("security", authenticated)
        public = document["paths"]["/ping"]["get"]
        self.assertEqual(public["security"], [])
        self.assertNotIn("401", public["responses"])
        self.assertEqual(document["security"], [{"bearerAuth": []}])

    def test_service_internal_error_is_documented_and_caught_once(self):
        result = {"kind": "named", "name": "sample::Result"}
        self.ir["service"] = {"title": "Sample", "version": "1.0", "servers": [],
                              "internal_error": {"type": result,
                                                 "description": "Internal server error"}}
        self.ir["operations"].append({
            "name": "list_results", "cpp_name": "sample::list_results", "method": "GET",
            "path": "/results", "parameters": [], "returns": result, "result": False,
            "errors": [{"status": 500, "type": result, "description": "Listing failed",
                        "exceptions": ["std::exception"]}],
        })
        document = convert(self.ir)
        self.assertEqual(document["paths"]["/results/{id}"]["get"]["responses"]["500"], {
            "description": "Internal server error",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Result"}}},
        })
        self.assertEqual(
            document["paths"]["/results"]["get"]["responses"]["500"]["description"],
            "Listing failed",
        )
        routes = generate_routes(self.ir, "codec.hpp")
        self.assertEqual(routes.count("catch (const std::exception& error)"), 2)
        self.assertIn('return response{500, encode_error<sample::Result>(500, error), '
                      '"get_result"};', routes)

    def test_method_not_allowed_is_opt_in_and_not_documented(self):
        result = {"kind": "named", "name": "sample::Result"}
        self.assertNotIn("response{405", generate_routes(self.ir, "codec.hpp"))
        self.ir["service"] = {"title": "Sample", "version": "1.0", "servers": [],
                              "method_not_allowed": {"type": result,
                                                     "description": "Method not allowed"}}
        self.ir["operations"].append({
            "name": "put_result", "cpp_name": "sample::put_result", "method": "PUT",
            "path": "/results/{id}",
            "parameters": [{"name": "id", "type": {"kind": "builtin", "name": "int"}}],
            "returns": result, "result": False,
        })
        routes = generate_routes(self.ir, "codec.hpp")
        # Both methods share the path's one check.
        self.assertEqual(routes.count("allowed.insert("), 1)
        self.assertIn('allowed.insert({"GET", "PUT"});', routes)
        self.assertIn("return response{405, encode_error<sample::Result>(405, error), "
                      '"", std::move(allow)};', routes)
        # A request with an operation's own method never gets the 405.
        document = convert(self.ir)
        for method in ("get", "put"):
            self.assertNotIn("405", document["paths"]["/results/{id}"][method]["responses"])

    def test_is_public_answers_false_without_public_operations(self):
        routes = generate_routes(self.ir, "codec.hpp")
        self.assertIn("inline bool is_public(const std::string& method, "
                      "const std::string& path) {\n    (void)method;", routes)

    def test_host_response_operation_is_documented_but_not_dispatched(self):
        result = {"kind": "named", "name": "sample::Result"}
        string = {"kind": "builtin", "name": "string"}
        self.ir["service"] = {"title": "Sample", "version": "1.0", "servers": [],
                              "bearer_auth": {"name": "bearerAuth", "format": "token"},
                              "unauthorized": {"type": result, "description": "Unauthorized"},
                              "internal_error": {"type": result, "description": "Failed"}}
        self.ir["operations"] += [{
            "name": "download", "cpp_name": "sample::download", "method": "GET",
            "path": "/downloads/{name}",
            "parameters": [{"name": "name", "type": string}],
            "returns": string, "result": False, "public": True,
            "host_response": "application/yaml",
            "errors": [{"status": 404, "type": result, "description": "Not found"}],
        }, {
            "name": "stream", "cpp_name": "sample::stream", "method": "GET",
            "path": "/results/7", "parameters": [],
            "returns": result, "result": False, "host_response": "application/json",
        }]
        # The integer placeholder route /results/{id} must not take /results/7.
        document = convert(self.ir)
        download = document["paths"]["/downloads/{name}"]["get"]
        self.assertEqual(download["responses"]["200"]["content"],
                         {"application/yaml": {"schema": {"type": "string"}}})
        self.assertEqual(sorted(download["responses"]), ["200", "404"])
        self.assertEqual(download["security"], [])
        self.assertEqual(download["parameters"][0]["in"], "path")
        stream = document["paths"]["/results/7"]["get"]["responses"]
        self.assertEqual(sorted(stream), ["200", "401"])
        routes = generate_routes(self.ir, "codec.hpp")
        self.assertNotIn("sample::download(", routes)
        self.assertNotIn("sample::stream(", routes)
        self.assertIn("return std::nullopt;  // stream is served by the host", routes)
        self.assertLess(routes.index("// stream is served by the host"),
                        routes.index("sample::get_result("))

    def test_free_form_objects_maps_and_success_status(self):
        obj = {"kind": "builtin", "name": "object"}
        self.ir["types"][0]["fields"] += [
            {"name": "context", "type": obj},
            {"name": "trace", "type": {"kind": "optional", "value": obj}, "nullable": True},
            {"name": "labels", "type": {"kind": "map", "values": {
                "kind": "builtin", "name": "string"}}},
        ]
        self.ir["operations"][0]["success_status"] = 201
        document = convert(self.ir)
        properties = document["components"]["schemas"]["Result"]["properties"]
        self.assertEqual(properties["context"], {"type": "object", "additionalProperties": True})
        self.assertEqual(properties["trace"],
                         {"type": ["object", "null"], "additionalProperties": True})
        self.assertEqual(properties["labels"],
                         {"type": "object", "additionalProperties": {"type": "string"}})
        responses = document["paths"]["/results/{id}"]["get"]["responses"]
        self.assertIn("201", responses)
        self.assertNotIn("200", responses)
        routes = generate_routes(self.ir, "codec.hpp")
        self.assertIn("return response{201, rig_json::encode(sample::get_result(", routes)

    def test_write_only_fields_and_records_without_required_fields(self):
        self.ir["types"][0]["fields"] = [{
            "name": "secret", "write_only": True,
            "type": {"kind": "optional", "value": {"kind": "builtin", "name": "string"}},
            "omit_empty": True,
        }]
        schema = convert(self.ir)["components"]["schemas"]["Result"]
        self.assertEqual(schema, {
            "type": "object", "additionalProperties": False,
            "properties": {"secret": {"type": "string", "writeOnly": True}},
        })

    def test_optional_values_use_null_types_and_references_use_any_of(self):
        string = {"kind": "builtin", "name": "string"}
        self.ir["types"][0]["fields"] += [
            {"name": "label", "type": {"kind": "optional", "value": string}},
            {"name": "parent", "type": {"kind": "optional", "value": {
                "kind": "named", "name": "sample::Result"}}},
            {"name": "heads", "type": {"kind": "map", "values": {
                "kind": "optional", "value": string}}},
        ]
        properties = convert(self.ir)["components"]["schemas"]["Result"]["properties"]
        self.assertEqual(properties["label"], {"type": ["string", "null"]})
        self.assertEqual(properties["parent"], {"anyOf": [
            {"$ref": "#/components/schemas/Result"}, {"type": "null"}]})
        self.assertEqual(properties["heads"], {
            "type": "object", "additionalProperties": {"type": ["string", "null"]}})

    def test_host_responses_document_headers(self):
        operation = self.ir["operations"][0]
        operation.update(returns={"kind": "builtin", "name": "string"},
                         host_response="application/octet-stream", response_format="binary",
                         response_headers=[{"name": "Content-Disposition",
                                            "description": "Attachment filename."}])
        response = convert(self.ir)["paths"]["/results/{id}"]["get"]["responses"]["200"]
        self.assertEqual(response["headers"], {"Content-Disposition": {
            "description": "Attachment filename.", "schema": {"type": "string"}}})
        self.assertEqual(response["content"], {"application/octet-stream": {
            "schema": {"type": "string", "format": "binary"}}})
        operation["response_headers"].append({"name": "content-disposition",
                                              "description": "Again."})
        with self.assertRaisesRegex(ValueError, "duplicate response header"):
            convert(self.ir)

    def test_documents_are_ordered_independently_of_declarations(self):
        result = {"kind": "named", "name": "sample::Result"}
        self.ir["types"].insert(0, {"kind": "record", "name": "Zebra", "cpp_name": "sample::Zebra",
                                    "fields": []})
        self.ir["operations"].insert(0, {
            "name": "zoo", "cpp_name": "sample::zoo", "method": "POST", "path": "/zoo",
            "parameters": [], "returns": {"kind": "named", "name": "sample::Zebra"},
            "result": False, "summary": "Zoo",
            "errors": [{"status": 409, "type": result}, {"status": 400, "type": result}],
        })
        document = convert(self.ir)
        self.assertEqual(list(document), ["openapi", "info", "paths", "components"])
        self.assertEqual(list(document["paths"]), ["/results/{id}", "/zoo"])
        self.assertEqual(list(document["components"]["schemas"]), ["Result", "RigInvalidRequest", "Zebra"])
        zoo = document["paths"]["/zoo"]["post"]
        self.assertEqual(list(zoo), ["operationId", "summary", "responses"])
        self.assertEqual(list(zoo["responses"]), ["200", "400", "409"])

    def test_yaml_and_json_describe_the_same_document(self):
        import yaml
        self.ir["operations"][0]["description"] = "Uses: colons, # hashes and 'quotes'."
        document = convert(self.ir)
        self.assertEqual(yaml.safe_load(dumps(document, "yaml")), document)
        self.assertEqual(json.loads(dumps(document, "json")), document)
        self.assertTrue(dumps(document, "yaml").endswith("\n"))

    def test_recursive_inline_record_is_rejected(self):
        self.ir["types"][0]["inline"] = True
        self.ir["types"][0]["fields"].append({
            "name": "children", "type": {"kind": "array", "items": {
                "kind": "named", "name": "sample::Result"}},
        })
        with self.assertRaisesRegex(ValueError, "recursive inline record"):
            convert(self.ir)

    def test_external_context_is_not_an_http_parameter(self):
        self.ir["operations"][0]["context_parameters"] = [
            {"name": "database", "position": 0}]
        document = convert(self.ir)
        operation = document["paths"]["/results/{id}"]["get"]
        self.assertEqual([item["name"] for item in operation["parameters"]], ["id"])
        # The id is still decoded, so its documented 400 remains.
        self.assertIn("400", operation["responses"])
        routes = generate_routes(self.ir, "codec.hpp")
        self.assertIn("template <typename Context>", routes)
        self.assertIn("sample::get_result(context.database, std::move(*argument_0))", routes)

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

    def test_optional_integer_choices_and_description(self):
        operation = self.ir["operations"][0]
        operation["path"] = "/results"
        operation["parameters"] = [{
            "name": "selected", "in": "query",
            "type": {"kind": "optional", "value": {"kind": "builtin", "name": "int"}},
            "int_values": [0, 1], "description": "Choose zero or one.",
        }]
        generated = convert(self.ir)["paths"]["/results"]["get"]
        self.assertEqual(generated["parameters"], [{
            "name": "selected", "in": "query", "required": False,
            "schema": {"type": "integer", "enum": [0, 1]},
            "description": "Choose zero or one.",
        }])

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
