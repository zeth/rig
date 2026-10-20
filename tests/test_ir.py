"""IR validation is shared by every generator."""

import copy
import unittest

from rig.http_routes import generate as http_routes
from rig.ir import validate
from rig.json_codec import generate as json_codec
from rig.openapi import convert


VALID = {
    "ir_version": 3,
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
        "errors": [{"status": 404, "type": {"kind": "named", "name": "sample::Error"}}],
    }],
}


class IRValidationTests(unittest.TestCase):
    def setUp(self):
        self.ir = copy.deepcopy(VALID)

    def test_valid_document_is_returned_unchanged(self):
        self.assertIs(validate(self.ir), self.ir)

    def test_structure_and_references(self):
        cases = [
            (lambda ir: ir.pop("types"), "missing types"),
            (lambda ir: ir.update(ir_version=True), "unsupported RIG IR version"),
            (lambda ir: ir.update(ir_version=2), "unsupported RIG IR version"),
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

    def test_same_short_type_name_in_another_namespace_is_valid(self):
        other = copy.deepcopy(self.ir["types"][0])
        other["cpp_name"] = "other::Item"
        self.ir["types"].append(other)
        self.assertIs(validate(self.ir), self.ir)

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
        self.assertLess(routes.index('method == "GET" && std::regex_match(path, match, route_1)'),
                        routes.index('method == "GET" && std::regex_match(path, match, route_0)'))

        variable["parameters"][0]["type"]["name"] = "int"
        self.assertIs(validate(self.ir), self.ir)
        literal["path"] = "/items/123"
        self.assertIs(validate(self.ir), self.ir)
        routes = http_routes(self.ir, "codec.hpp")
        self.assertLess(routes.index('method == "GET" && std::regex_match(path, match, route_1)'),
                        routes.index('method == "GET" && std::regex_match(path, match, route_0)'))


if __name__ == "__main__":
    unittest.main()
