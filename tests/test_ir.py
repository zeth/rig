"""IR validation is shared by every generator."""

import copy
import unittest

from rig.http_routes import generate as http_routes
from rig.ir import validate
from rig.json_codec import generate as json_codec
from rig.openapi import convert


VALID = {
    "ir_version": 12,
    "types": [
        {"kind": "record", "name": "Item", "cpp_name": "sample::Item", "fields": [
            {"name": "id", "type": {"kind": "builtin", "name": "int"}},
        ]},
        {"kind": "record", "name": "Error", "cpp_name": "sample::Error", "fields": [
            {"name": "message", "type": {"kind": "builtin", "name": "string"}},
        ]},
    ],
    "operations": [{
        "name": "get_item", "cpp_name": "sample::get_item", "method": "GET", "path": "/items/{id}",
        "parameters": [{"name": "id", "type": {"kind": "builtin", "name": "int"}}],
        "returns": {"kind": "named", "name": "sample::Item"},
        "result": True,
        "errors": [{"status": 404, "type": {"kind": "named", "name": "sample::Error"}}],
    }],
}


class IRValidationTests(unittest.TestCase):
    def setUp(self):
        self.ir = copy.deepcopy(VALID)

    def test_valid_document_is_returned_unchanged(self):
        self.assertIs(validate(self.ir), self.ir)

    def test_inline_is_a_record_boolean(self):
        self.ir["types"][0]["inline"] = True
        self.assertIs(validate(self.ir), self.ir)
        self.ir["types"][0]["inline"] = "yes"
        with self.assertRaisesRegex(ValueError, "inline: expected boolean"):
            validate(self.ir)
        self.ir["types"][0]["inline"] = True
        self.ir["types"][1]["kind"] = "enum"
        self.ir["types"][1]["values"] = ["one"]
        self.ir["types"][1].pop("fields")
        self.ir["types"][1]["inline"] = True
        with self.assertRaisesRegex(ValueError, "unknown key inline"):
            validate(self.ir)

    def test_integer_range_validation(self):
        parameter = self.ir["operations"][0]["parameters"][0]
        parameter["range"] = {"minimum": 1, "maximum": 20}
        self.assertIs(validate(self.ir), self.ir)
        for bounds, message in (
            ({"minimum": 21, "maximum": 20}, "minimum exceeds maximum"),
            ({"minimum": True, "maximum": 20}, "bounds must be integers"),
            ({"minimum": 1, "maximum": 2 ** 31}, "bounds must fit C\\+\\+ int"),
            ({"minimum": 1}, "missing maximum"),
        ):
            with self.subTest(bounds=bounds), self.assertRaisesRegex(ValueError, message):
                parameter["range"] = bounds
                validate(self.ir)
        parameter["range"] = {"minimum": 1, "maximum": 20}
        parameter["type"] = {"kind": "builtin", "name": "string"}
        with self.assertRaisesRegex(ValueError, "requires int or optional<int>"):
            validate(self.ir)

    def test_integer_choices_and_parameter_description_validation(self):
        parameter = self.ir["operations"][0]["parameters"][0]
        parameter["int_values"] = [0, 1]
        parameter["description"] = "Choose zero or one."
        self.assertIs(validate(self.ir), self.ir)
        for values in ([0, 0], [True, 1], [], [2 ** 31]):
            with self.subTest(values=values), self.assertRaisesRegex(
                ValueError, "expected unique C\\+\\+ integers"
            ):
                parameter["int_values"] = values
                validate(self.ir)
        parameter["int_values"] = [0, 1]
        parameter["range"] = {"minimum": 0, "maximum": 1}
        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            validate(self.ir)
        parameter.pop("range")
        parameter["description"] = ""
        with self.assertRaisesRegex(ValueError, "expected nonempty text"):
            validate(self.ir)

    def test_boolean_value_and_operation_text_validation(self):
        field = self.ir["types"][0]["fields"][0]
        field["bool_value"] = True
        with self.assertRaisesRegex(ValueError, "requires a bool field"):
            validate(self.ir)
        field["type"] = {"kind": "builtin", "name": "bool"}
        self.assertIs(validate(self.ir), self.ir)
        field["bool_value"] = 1
        with self.assertRaisesRegex(ValueError, "requires a bool field"):
            validate(self.ir)
        field["bool_value"] = False
        self.ir["operations"][0]["summary"] = ""
        with self.assertRaisesRegex(ValueError, "expected nonempty text"):
            validate(self.ir)

    def test_string_choices_require_a_string_field(self):
        field = self.ir["types"][0]["fields"][0]
        field["string_values"] = ["live", "trashed"]
        with self.assertRaisesRegex(ValueError, "requires a string field"):
            validate(self.ir)
        field["type"]["name"] = "string"
        self.assertIs(validate(self.ir), self.ir)
        for choices in ([], ["live", "live"], [""], [7], ["x" * 64]):
            with self.subTest(choices=choices), self.assertRaisesRegex(
                ValueError, "expected unique nonempty strings"
            ):
                field["string_values"] = choices
                validate(self.ir)
        field["string_values"] = ["live", "trashed"]
        field["type"] = {"kind": "optional", "value": {
            "kind": "builtin", "name": "string"}}
        with self.assertRaisesRegex(ValueError, "requires a string field"):
            validate(self.ir)
        field["omit_empty"] = True
        self.assertIs(validate(self.ir), self.ir)

    def test_error_description_must_be_nonempty(self):
        self.ir["operations"][0]["errors"][0]["description"] = ""
        with self.assertRaisesRegex(ValueError, "expected nonempty text"):
            validate(self.ir)

    def test_validation_error_is_a_registered_body_with_description(self):
        self.ir["service"] = {"title": "Sample", "version": "1.0", "servers": [],
                              "validation_error": {
                                  "type": {"kind": "named", "name": "sample::Error"},
                                  "description": "Bad request"}}
        self.assertIs(validate(self.ir), self.ir)
        cases = (
            ({"type": {"kind": "named", "name": "sample::Missing"}, "description": "Bad"},
             "unregistered type"),
            ({"type": {"kind": "named", "name": "sample::Error"}, "description": ""},
             "expected nonempty text"),
            ({"type": {"kind": "named", "name": "sample::Error"}}, "missing description"),
        )
        for validation, message in cases:
            with self.subTest(message=message):
                document = copy.deepcopy(self.ir)
                document["service"]["validation_error"] = validation
                with self.assertRaisesRegex(ValueError, message):
                    validate(document)

    def test_service_unauthorized_response_and_public_operations(self):
        error = {"kind": "named", "name": "sample::Error"}
        self.ir["service"] = {"title": "Sample", "version": "1.0", "servers": [],
                              "bearer_auth": {"name": "bearerAuth", "format": "token"},
                              "unauthorized": {"type": error, "description": "Unauthorized"}}
        self.ir["operations"][0]["public"] = True
        self.ir["operations"][0]["errors"].append({"status": 401, "type": error})
        self.assertIs(validate(self.ir), self.ir)
        cases = (
            (lambda ir: ir["operations"][0].pop("public"), "401 is declared by the service"),
            (lambda ir: ir["operations"][0].update(public=False), "expected true"),
            (lambda ir: ir["service"].pop("bearer_auth"), "unauthorized: requires bearer_auth"),
            (lambda ir: [ir["service"].pop(key) for key in ("bearer_auth", "unauthorized")],
             "public: requires service bearer_auth"),
        )
        for change, message in cases:
            with self.subTest(message=message):
                document = copy.deepcopy(self.ir)
                change(document)
                with self.assertRaisesRegex(ValueError, message):
                    validate(document)

    def test_host_response_operations(self):
        string = {"kind": "builtin", "name": "string"}
        operation = self.ir["operations"][0]
        operation.update(returns=string, host_response="text/event-stream")
        self.assertIs(validate(self.ir), self.ir)
        for media_range in ("*/*", "text/*"):
            with self.subTest(media_range=media_range):
                document = copy.deepcopy(self.ir)
                document["operations"][0]["host_response"] = media_range
                self.assertIs(validate(document), document)
        cases = (
            (lambda op: op.update(host_response="yaml"), "expected a media type"),
            (lambda op: op.update(host_response="*/json"), "expected a media type"),
            (lambda op: op.update(returns={"kind": "named", "name": "sample::Item"}),
             "requires a string return"),
            (lambda op: op.update(context_parameters=[{"name": "db", "position": 0}]),
             "no context parameters"),
            (lambda op: op["errors"][0].update(exceptions=["sample::Missing"]),
             "the host maps"),
        )
        for change, message in cases:
            with self.subTest(message=message):
                document = copy.deepcopy(self.ir)
                change(document["operations"][0])
                with self.assertRaisesRegex(ValueError, message):
                    validate(document)
        operation.update(host_response="application/json",
                         returns={"kind": "named", "name": "sample::Item"})
        self.assertIs(validate(self.ir), self.ir)

    def test_minimum_applies_to_int_or_omittable_optional_int(self):
        field = self.ir["types"][0]["fields"][0]
        field["minimum"] = 0
        self.assertIs(validate(self.ir), self.ir)
        field["type"] = {"kind": "optional", "value": {"kind": "builtin", "name": "int"}}
        with self.assertRaisesRegex(ValueError, "requires an int field"):
            validate(self.ir)
        field["omit_empty"] = True
        self.assertIs(validate(self.ir), self.ir)
        self.assertEqual(convert(self.ir)["components"]["schemas"]["Item"]["properties"]["id"],
                         {"type": "integer", "minimum": 0})

    def test_value_constraints_must_suit_their_types(self):
        integer = {"kind": "builtin", "name": "int"}
        string = {"kind": "builtin", "name": "string"}
        operation = self.ir["operations"][0]
        operation["parameters"].append({"name": "q", "in": "query", "type": string})
        cases = (
            ({"format": "Not A Format"}, string, "expected a format name"),
            ({"min_length": 1}, integer, "requires a string"),
            ({"min_length": 5, "max_length": 2}, string, "min_length exceeds max_length"),
            ({"default": 3}, string, "does not match the value type"),
            ({"default": True}, integer, "does not match the value type"),
            ({"string_values": ["a"], "default": "b"}, string, "not one of the string_values"),
            ({"string_values": ["a"]}, integer, "requires a string"),
            ({"minimum": 0}, string, "requires an int parameter"),
            ({"minimum": 0, "range": {"minimum": 0, "maximum": 1}}, integer,
             "duplicates a range"),
            ({"default": "x"}, {"kind": "optional", "value": string},
             "whose type is not optional"),
        )
        for extra, ref, message in cases:
            with self.subTest(message=message, extra=extra):
                document = copy.deepcopy(self.ir)
                document["operations"][0]["parameters"][1].update(extra, type=ref)
                with self.assertRaisesRegex(ValueError, message):
                    validate(document)
        field = self.ir["types"][0]["fields"][0]
        field.update(type={"kind": "optional", "value": integer}, omit_empty=True, default=1)
        with self.assertRaisesRegex(ValueError, "a defaulted field is not optional"):
            validate(self.ir)

    def test_value_types_and_base_records(self):
        string = {"kind": "builtin", "name": "string"}
        value = {"kind": "record", "name": "Ref", "cpp_name": "sample::Ref", "value": True,
                 "fields": [{"name": "value", "type": string, "pattern": "^[0-9a-f]+$"}]}
        derived = {"kind": "record", "name": "Detail", "cpp_name": "sample::Detail",
                   "base": "sample::Item", "fields": [{"name": "note", "type": string}]}
        self.ir["types"] += [value, derived]
        self.ir["operations"][0]["parameters"].append(
            {"name": "at", "in": "query", "type": {"kind": "named", "name": "sample::Ref"}})
        self.assertIs(validate(self.ir), self.ir)
        cases = (
            (lambda ir: ir["types"][2]["fields"].append({"name": "x", "type": string}),
             "exactly one required field"),
            (lambda ir: ir["types"][3].update(base="sample::Ref"), "expected a registered record"),
            (lambda ir: ir["types"][3].update(base="sample::Missing"), "expected a registered record"),
            (lambda ir: ir["types"][3]["fields"].append(
                {"name": "id", "type": {"kind": "builtin", "name": "int"}}), "hides a base field"),
            (lambda ir: ir["types"][0].update(base="sample::Detail"), "in a cycle"),
            (lambda ir: ir["types"][2]["fields"][0].update(type={"kind": "builtin", "name": "int"}),
             "pattern: requires a string"),
        )
        for change, message in cases:
            with self.subTest(message=message):
                document = copy.deepcopy(self.ir)
                change(document)
                with self.assertRaisesRegex(ValueError, message):
                    validate(document)

    def test_host_response_details_require_a_host_response(self):
        string = {"kind": "builtin", "name": "string"}
        operation = self.ir["operations"][0]
        operation.update(returns=string, host_response="text/plain", response_values=["pong"],
                         response_format="binary", operation_id="get_item",
                         success_responses=[{"status": 201, "description": "Created"}])
        self.assertIs(validate(self.ir), self.ir)
        cases = (
            (lambda op: op.pop("host_response"), "requires host_response"),
            (lambda op: op.update(response_values=[]), "expected unique strings"),
            (lambda op: op.update(response_format="Binary!"), "expected a format"),
            (lambda op: op.update(operation_id="not valid"), "invalid C"),
            (lambda op: op["success_responses"].append({"status": 200, "description": "Same"}),
             "another 2xx status"),
            (lambda op: op["success_responses"].append({"status": 204, "description": "Empty"}),
             "another 2xx status"),
        )
        for change, message in cases:
            with self.subTest(message=message):
                document = copy.deepcopy(self.ir)
                change(document["operations"][0])
                with self.assertRaisesRegex(ValueError, message):
                    validate(document)

    def test_chosen_status_needs_declared_statuses_on_a_generated_operation(self):
        operation = self.ir["operations"][0]
        operation.update(chosen_status=True, result=False, errors=[],
                         success_responses=[{"status": 201, "description": "Created"}])
        self.assertIs(validate(self.ir), self.ir)
        cases = (
            (lambda op: op.update(chosen_status=False), "expected true"),
            (lambda op: op.pop("success_responses"), "requires success_responses"),
            (lambda op: op.update(result=True), "without a result"),
            (lambda op: op.update(returns={"kind": "builtin", "name": "string"},
                                  host_response="text/plain"), "without a result"),
            (lambda op: op.pop("chosen_status"), "requires host_response or chosen_status"),
        )
        for change, message in cases:
            with self.subTest(message=message):
                document = copy.deepcopy(self.ir)
                change(document["operations"][0])
                with self.assertRaisesRegex(ValueError, message):
                    validate(document)

    def test_header_parameters_and_events_need_host_responses(self):
        string = {"kind": "builtin", "name": "string"}
        operation = self.ir["operations"][0]
        operation.update(returns=string, host_response="text/event-stream",
                         sse_events=[{"name": "ready", "type": {"kind": "named", "name": "sample::Item"}}],
                         success_responses=[{"status": 204, "description": "Finished"}])
        operation["parameters"].append({"name": "cursor", "in": "header", "header": "Last-Event-ID",
                                        "type": {"kind": "optional", "value": string}})
        self.assertIs(validate(self.ir), self.ir)
        cases = (
            (lambda op: op.update(host_response="application/json"),
             "require a text/event-stream host response"),
            (lambda op: op["parameters"][1].update(header="Bad Header"), "expected an HTTP header name"),
            (lambda op: op["parameters"][1].update(type={"kind": "builtin", "name": "int"}),
             "a header parameter is a string"),
            (lambda op: op["sse_events"].append(dict(op["sse_events"][0])), "duplicate event"),
            (lambda op: [op.pop("host_response"), op.pop("sse_events"),
                         op.pop("success_responses")],
             "header parameters require host_response"),
            (lambda op: op["success_responses"].append({"status": 205, "description": "Reset"}),
             "or 204 for an event stream"),
        )
        for change, message in cases:
            with self.subTest(message=message):
                document = copy.deepcopy(self.ir)
                change(document["operations"][0])
                with self.assertRaisesRegex(ValueError, message):
                    validate(document)

    def test_success_status_is_a_2xx_with_a_body(self):
        for status in (201, 202, 299):
            self.ir["operations"][0]["success_status"] = status
            self.assertIs(validate(self.ir), self.ir)
        for status in (199, 204, 205, 300, "201", True):
            with self.subTest(status=status):
                document = copy.deepcopy(self.ir)
                document["operations"][0]["success_status"] = status
                with self.assertRaisesRegex(ValueError, "expected a 2xx status with a body"):
                    validate(document)

    def test_map_values_are_type_references(self):
        field = self.ir["types"][0]["fields"][0]
        field["type"] = {"kind": "map", "values": {"kind": "builtin", "name": "object"}}
        self.assertIs(validate(self.ir), self.ir)
        field["type"] = {"kind": "map", "values": {"kind": "named", "name": "Missing"}}
        with self.assertRaisesRegex(ValueError, "unregistered type"):
            validate(self.ir)
        field["type"] = {"kind": "map"}
        with self.assertRaisesRegex(ValueError, "missing values"):
            validate(self.ir)

    def test_mapped_exceptions_are_unique_qualified_names(self):
        operation = self.ir["operations"][0]
        operation["errors"][0]["exceptions"] = ["sample::NotFound", "std::out_of_range"]
        self.assertIs(validate(self.ir), self.ir)
        cases = (
            ([], "expected exception types"),
            (["sample::bad-name"], "invalid qualified C\\+\\+ name"),
            (["sample::NotFound", "sample::NotFound"], "duplicate mapped exception"),
        )
        for exceptions, message in cases:
            with self.subTest(message=message):
                document = copy.deepcopy(self.ir)
                document["operations"][0]["errors"][0]["exceptions"] = exceptions
                with self.assertRaisesRegex(ValueError, message):
                    validate(document)
        operation["errors"].append({"status": 500, "type": {"kind": "named", "name": "sample::Error"},
                                    "exceptions": ["sample::NotFound"]})
        with self.assertRaisesRegex(ValueError, "duplicate mapped exception"):
            validate(self.ir)

    def test_mapped_exceptions_are_caught_in_declaration_order(self):
        operation = self.ir["operations"][0]
        operation["result"] = False
        operation["errors"] = [
            {"status": 404, "type": {"kind": "named", "name": "sample::Error"},
             "exceptions": ["sample::NotFound"]},
            {"status": 500, "type": {"kind": "named", "name": "sample::Error"},
             "exceptions": ["std::exception"]},
            {"status": 401, "type": {"kind": "named", "name": "sample::Error"}},
        ]
        routes = http_routes(self.ir, "codec.hpp")
        self.assertIn("rig_error_body(std::type_identity<Body>{}, status, error)", routes)
        not_found = routes.index("catch (const sample::NotFound& error)")
        fallback = routes.index("catch (const std::exception& error)")
        self.assertLess(not_found, fallback)
        self.assertIn('return response{404, encode_error<sample::Error>(404, error), "get_item"};',
                      routes)
        self.assertNotIn("401, encode_error", routes)
        self.assertEqual(convert(self.ir), convert(
            {**self.ir, "operations": [{**operation, "errors": [
                {key: value for key, value in error.items() if key != "exceptions"}
                for error in operation["errors"]
            ]}]}
        ))

    def test_routes_without_mapped_exceptions_need_no_error_body(self):
        self.assertNotIn("rig_error_body", http_routes(self.ir, "codec.hpp"))

    def test_documented_server_error_does_not_change_function_return(self):
        operation = self.ir["operations"][0]
        operation["result"] = False
        routes = http_routes(self.ir, "codec.hpp")
        self.assertIn("rig_json::encode(sample::get_item(", routes)
        self.assertNotIn("const auto outcome = sample::get_item(", routes)
        operation["result"] = True
        self.assertIn("const auto outcome = sample::get_item(",
                      http_routes(self.ir, "codec.hpp"))
        operation["result"] = 1
        with self.assertRaisesRegex(ValueError, "result: expected boolean"):
            validate(self.ir)

    def test_generated_responses_identify_the_matched_operation(self):
        routes = http_routes(self.ir, "codec.hpp")
        self.assertIn('invalid_request(error, "get_item")', routes)
        self.assertIn('rig_json::encode(value), "get_item"', routes)
        self.assertIn('rig_json::encode(value.body), "get_item"', routes)
        self.ir["operations"][0]["result"] = False
        self.assertIn('rig_json::encode(sample::get_item(std::move(*argument_0))), "get_item"',
                      http_routes(self.ir, "codec.hpp"))

    def test_open_record_flag_must_be_boolean(self):
        self.ir["types"][0]["open"] = "yes"
        with self.assertRaisesRegex(ValueError, "expected boolean"):
            validate(self.ir)

    def test_service_metadata_validation(self):
        self.ir["service"] = {
            "title": "Example API", "version": "0.1.0", "servers": ["/"],
            "bearer_auth": {"name": "bearerAuth", "format": "token"},
        }
        self.assertIs(validate(self.ir), self.ir)
        self.ir["service"]["servers"] = [""]
        with self.assertRaisesRegex(ValueError, "expected nonempty URL"):
            validate(self.ir)
        self.ir["service"]["servers"] = ["/"]
        self.ir["service"]["method_not_allowed"] = {"type": {"kind": "named", "name": "Missing"},
                                                    "description": "Method not allowed"}
        with self.assertRaisesRegex(ValueError, "method_not_allowed.type"):
            validate(self.ir)
        del self.ir["service"]["method_not_allowed"]
        self.ir["service"]["bearer_auth"]["name"] = "bad-name"
        with self.assertRaisesRegex(ValueError, "invalid C\\+\\+ identifier"):
            validate(self.ir)

    def test_structure_and_references(self):
        cases = [
            (lambda ir: ir.pop("types"), "missing types"),
            (lambda ir: ir.update(ir_version=True), "unsupported RIG IR version"),
            (lambda ir: ir.update(ir_version=3), "unsupported RIG IR version"),
            (lambda ir: ir["types"].append(copy.deepcopy(ir["types"][0])), "duplicate type name"),
            (lambda ir: ir["types"][0].update(cpp_name="sample::Other"), "does not match cpp_name"),
            (lambda ir: ir["types"][0].update(cpp_name="sample::bad-name"), "invalid qualified C\\+\\+ name"),
            (lambda ir: ir["operations"][0].update(cpp_name="sample::other"), "does not match cpp_name"),
            (lambda ir: ir["types"][0]["fields"].append(copy.deepcopy(ir["types"][0]["fields"][0])), "duplicate field"),
            (lambda ir: ir["types"][0]["fields"][0]["type"].update(name="Missing", kind="named"), "unregistered type"),
            (lambda ir: ir["types"][0]["fields"][0]["type"].update(name=[]), "unsupported builtin type"),
            (lambda ir: ir["operations"][0].update(method=[]), "unsupported HTTP method"),
            (lambda ir: ir["operations"][0]["parameters"].clear(), "unbound placeholders"),
            (lambda ir: ir["operations"][0].update(path="/items/{id}/{id}"), "duplicate route parameter"),
            (lambda ir: ir["operations"][0].update(path="/items/{id}/"), "unsupported route path"),
            (lambda ir: ir["operations"][0]["parameters"].append({"name": "body", "type": {"kind": "named", "name": "sample::Item"}}), "body with GET"),
            (lambda ir: ir["operations"][0]["parameters"][0].update({"in": "query"}), "query parameter is also a path placeholder"),
            (lambda ir: ir["operations"][0]["parameters"][0].update({"in": "cookie"}), "unsupported parameter location"),
            (lambda ir: ir["operations"][0].update(path="/items"), "body with GET"),
            (lambda ir: ir["operations"][0]["errors"].append(copy.deepcopy(ir["operations"][0]["errors"][0])), "duplicate response status"),
            (lambda ir: ir["operations"].append(copy.deepcopy(ir["operations"][0])), "duplicate operation name"),
        ]
        for change, message in cases:
            with self.subTest(message=message):
                document = copy.deepcopy(self.ir)
                change(document)
                with self.assertRaisesRegex(ValueError, message):
                    validate(document)

    def test_all_generators_reject_the_same_invalid_ir(self):
        self.ir["types"][0]["fields"][0]["type"] = {"kind": "named", "name": "Missing"}
        generators = (
            lambda: convert(self.ir),
            lambda: json_codec(self.ir, "api.hpp"),
            lambda: http_routes(self.ir, "codec.hpp"),
        )
        for generate in generators:
            with self.subTest(generator=generate):
                with self.assertRaisesRegex(ValueError, "unregistered type"):
                    generate()

    def test_query_parameter_must_be_scalar(self):
        operation = self.ir["operations"][0]
        operation["path"] = "/items"
        operation["parameters"][0] = {
            "name": "filter", "type": {"kind": "named", "name": "sample::Item"},
            "in": "query",
        }
        with self.assertRaisesRegex(ValueError, "query parameter must be scalar"):
            validate(self.ir)

    def test_optional_query_parameter_must_contain_scalar(self):
        operation = self.ir["operations"][0]
        operation["path"] = "/items"
        operation["parameters"][0] = {
            "name": "filter", "in": "query",
            "type": {"kind": "optional", "value": {
                "kind": "named", "name": "sample::Item",
            }},
        }
        with self.assertRaisesRegex(ValueError, "query parameter must be scalar"):
            validate(self.ir)
        operation["parameters"][0]["type"]["value"] = {"kind": "builtin", "name": "int"}
        self.assertIs(validate(self.ir), self.ir)

    def test_same_short_type_name_in_another_namespace_is_valid(self):
        other = copy.deepcopy(self.ir["types"][0])
        other["cpp_name"] = "other::Item"
        self.ir["types"].append(other)
        self.assertIs(validate(self.ir), self.ir)

    def test_context_positions_follow_the_cpp_signature(self):
        operation = self.ir["operations"][0]
        operation["context_parameters"] = [
            {"name": "database", "position": 0},
            {"name": "audit", "position": 2},
        ]
        routes = http_routes(self.ir, "codec.hpp")
        self.assertIn(
            "sample::get_item(context.database, std::move(*argument_0), context.audit)",
            routes,
        )
        operation["context_parameters"][1]["position"] = 0
        with self.assertRaisesRegex(ValueError, "duplicate context parameter position"):
            validate(self.ir)
        operation["context_parameters"][1]["position"] = 3
        with self.assertRaisesRegex(ValueError, "invalid parameter position"):
            validate(self.ir)

    def test_equivalent_parameterized_paths_are_rejected(self):
        other = copy.deepcopy(self.ir["operations"][0])
        other["name"] = "get_by_slug"
        other["cpp_name"] = "sample::get_by_slug"
        other["path"] = "/items/{slug}"
        other["parameters"] = [{
            "name": "slug", "type": {"kind": "builtin", "name": "string"},
        }]
        self.ir["operations"].append(other)
        with self.assertRaisesRegex(ValueError, "ambiguous routes"):
            validate(self.ir)

    def test_crossing_route_specificity_is_rejected(self):
        first = self.ir["operations"][0]
        first["path"] = "/{group}/fixed"
        first["parameters"] = [{
            "name": "group", "type": {"kind": "builtin", "name": "string"},
        }]
        second = copy.deepcopy(first)
        second["name"] = "get_other"
        second["cpp_name"] = "sample::get_other"
        second["path"] = "/known/{item}"
        second["parameters"] = [{
            "name": "item", "type": {"kind": "builtin", "name": "string"},
        }]
        self.ir["operations"].append(second)
        with self.assertRaisesRegex(ValueError, "ambiguous routes"):
            validate(self.ir)

    def test_disjoint_routes_and_literal_precedence(self):
        variable = self.ir["operations"][0]
        variable["parameters"][0]["type"]["name"] = "string"
        literal = copy.deepcopy(variable)
        literal["name"] = "get_new"
        literal["cpp_name"] = "sample::get_new"
        literal["path"] = "/items/new"
        literal["parameters"] = []
        self.ir["operations"].append(literal)
        self.assertIs(validate(self.ir), self.ir)
        routes = http_routes(self.ir, "codec.hpp")
        self.assertLess(routes.index('method == "GET" && std::regex_match(route_path, match, route_1)'),
                        routes.index('method == "GET" && std::regex_match(route_path, match, route_0)'))

        variable["parameters"][0]["type"]["name"] = "int"
        self.assertIs(validate(self.ir), self.ir)
        literal["path"] = "/items/123"
        self.assertIs(validate(self.ir), self.ir)
        routes = http_routes(self.ir, "codec.hpp")
        self.assertLess(routes.index('method == "GET" && std::regex_match(route_path, match, route_1)'),
                        routes.index('method == "GET" && std::regex_match(route_path, match, route_0)'))


if __name__ == "__main__":
    unittest.main()
