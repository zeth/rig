"""IR validation is shared by every generator."""

import copy
import unittest

from rig.http_routes import generate as http_routes
from rig.ir import validate
from rig.json_codec import generate as json_codec
from rig.openapi import convert


VALID = {
    "ir_version": 2,
    "types": [
        {"kind": "record", "name": "Item", "fields": [
            {"name": "id", "type": {"kind": "builtin", "name": "int"}},
        ]},
        {"kind": "record", "name": "Error", "fields": [
            {"name": "message", "type": {"kind": "builtin", "name": "string"}},
        ]},
    ],
    "operations": [{
        "name": "get_item", "method": "GET", "path": "/items/{id}",
        "parameters": [{"name": "id", "type": {"kind": "builtin", "name": "int"}}],
        "returns": {"kind": "named", "name": "Item"},
        "errors": [{"status": 404, "type": {"kind": "named", "name": "Error"}}],
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
            (lambda ir: ir["types"].append(copy.deepcopy(ir["types"][0])), "duplicate type name"),
            (lambda ir: ir["types"][0]["fields"].append(copy.deepcopy(ir["types"][0]["fields"][0])), "duplicate field"),
            (lambda ir: ir["types"][0]["fields"][0]["type"].update(name="Missing", kind="named"), "unregistered type"),
            (lambda ir: ir["types"][0]["fields"][0]["type"].update(name=[]), "unsupported builtin type"),
            (lambda ir: ir["operations"][0].update(method=[]), "unsupported HTTP method"),
            (lambda ir: ir["operations"][0]["parameters"].clear(), "unbound placeholders"),
            (lambda ir: ir["operations"][0].update(path="/items/{id}/{id}"), "duplicate route parameter"),
            (lambda ir: ir["operations"][0].update(path="/items/{id}/"), "unsupported route path"),
            (lambda ir: ir["operations"][0]["parameters"].append({"name": "body", "type": {"kind": "named", "name": "Item"}}), "body with GET"),
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
            lambda: json_codec(self.ir, "sample", "api.hpp"),
            lambda: http_routes(self.ir, "sample", "codec.hpp"),
        )
        for generate in generators:
            with self.subTest(generator=generate):
                with self.assertRaisesRegex(ValueError, "unregistered type"):
                    generate()


if __name__ == "__main__":
    unittest.main()
