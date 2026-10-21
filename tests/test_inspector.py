"""The installed command owns C++26 compilation and validates its output."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from rig.json_codec import generate as generate_codec


class InspectorTests(unittest.TestCase):
    def run_inspect(self, directory, *arguments):
        return subprocess.run(
            [sys.executable, "-m", "rig", "inspect", *arguments],
            cwd=directory, text=True, capture_output=True,
        )

    def test_codec_preserves_omitted_and_null_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "api.hpp").write_text(
                '#include <optional>\n#include <string>\n'
                'namespace sample { struct Item { long long count; double percent; '
                'std::optional<std::string> label; '
                'std::optional<std::optional<std::string>> error; }; }\n'
            )
            string = {"kind": "builtin", "name": "string"}
            optional_string = {"kind": "optional", "value": string}
            ir = {"ir_version": 12, "types": [{
                "kind": "record", "name": "Item", "cpp_name": "sample::Item",
                "fields": [
                    {"name": "count", "type": {"kind": "builtin", "name": "int64"}},
                    {"name": "percent", "type": {"kind": "builtin", "name": "double"}},
                    {"name": "label", "type": optional_string, "omit_empty": True},
                    {"name": "error", "type": {"kind": "optional", "value": optional_string},
                     "omit_empty": True, "nullable": True},
                ],
            }], "operations": []}
            (root / "codec.hpp").write_text(generate_codec(ir, "api.hpp"))
            (root / "check.cpp").write_text(
                '#include "codec.hpp"\n'
                'int main() {\n'
                '  sample::Item item{42, 0.5, std::nullopt, '
                'std::optional<std::optional<std::string>>{std::in_place, std::nullopt}};\n'
                '  auto value = rig_json::encode(item);\n'
                '  if (value.contains("label") || !value.at("error").is_null()) return 1;\n'
                '  auto decoded = rig_json::decode<sample::Item>(value);\n'
                '  if (decoded.count != 42 || decoded.percent != 0.5 || '
                'decoded.label || !decoded.error || *decoded.error) return 2;\n'
                '  value.erase("error");\n'
                '  if (rig_json::decode<sample::Item>(value).error) return 3;\n'
                '  value["extra"] = 1;\n'
                '  try { (void)rig_json::decode<sample::Item>(value); return 4; }\n'
                '  catch (const std::invalid_argument&) {}\n'
                '}\n'
            )
            include_dir = Path(__file__).resolve().parents[1] / "src" / "rig" / "include"
            binary = root / "check"
            compiled = subprocess.run(
                ["g++", "-std=c++20", f"-I{include_dir}", "-I.", "check.cpp", "-o", str(binary)],
                cwd=directory, text=True, capture_output=True,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            run = subprocess.run([binary], cwd=directory, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_compiles_with_forwarded_include_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            header = root / "include" / "sample" / "api.hpp"
            header.parent.mkdir(parents=True)
            header.write_text(
                '#include <rig/route.hpp>\n'
                '#include <optional>\n#include <string>\n'
                'namespace sample {\n'
                'struct Context;\n'
                'struct Item { int value RIG_MINIMUM(1) RIG_FIELD_DESCRIPTION("Count"); '
                'long long updated_at; double percent; '
                'std::optional<std::string> label RIG_OMIT_EMPTY; '
                'std::optional<std::string> error RIG_NULLABLE; '
                'std::string state RIG_STRING_VALUES("live", "trashed"); };\n'
                'struct RIG_INLINE_RECORD Detail { std::string name; };\n'
                'RIG_ROUTE(GET, "/items/{id}") Item get_item(Context& context RIG_CONTEXT, int id);\n'
                'RIG_ROUTE(GET, "/items") Item list_items(int limit RIG_QUERY RIG_RANGE(1, 20));\n'
                'RIG_ROUTE(GET, "/choices") Item choices('
                'std::optional<int> selected RIG_QUERY RIG_INT_VALUES(0, 1) '
                'RIG_PARAMETER_DESCRIPTION("Choose zero or one"));\n'
                'RIG_ROUTE(GET, "/detail") Detail get_detail();\n'
                '}\n'
            )
            (root / "inspect.cpp").write_text(
                '#include <sample/api.hpp>\n'
                '#include <rig/inspect.hpp>\n'
                '#include <iostream>\n'
                'int main() { rig::writer out(std::cout); '
                'out.add_namespace<^^sample>(); out.finish(); }\n'
            )
            result = self.run_inspect(root, "inspect.cpp", "--", "-Iinclude")
            self.assertEqual(result.returncode, 0, result.stderr)
            ir = json.loads(result.stdout)
            self.assertEqual(ir["ir_version"], 12)
            self.assertEqual(ir["operations"][0]["path"], "/items/{id}")
            self.assertIs(ir["operations"][0]["result"], False)
            self.assertEqual(ir["operations"][0]["context_parameters"],
                             [{"name": "context", "position": 0}])
            self.assertEqual([p["name"] for p in ir["operations"][0]["parameters"]], ["id"])
            self.assertEqual(ir["operations"][1]["parameters"][0]["in"], "query")
            self.assertEqual(ir["operations"][1]["parameters"][0]["range"],
                             {"minimum": 1, "maximum": 20})
            self.assertEqual(ir["operations"][2]["parameters"][0]["int_values"], [0, 1])
            self.assertEqual(ir["operations"][2]["parameters"][0]["description"],
                             "Choose zero or one")
            self.assertEqual(ir["types"][0]["fields"][0]["name"], "value")
            self.assertEqual(ir["types"][0]["fields"][0]["minimum"], 1)
            self.assertEqual(ir["types"][0]["fields"][0]["description"], "Count")
            self.assertEqual(ir["types"][0]["fields"][1]["type"]["name"], "int64")
            self.assertEqual(ir["types"][0]["fields"][2]["type"]["name"], "double")
            self.assertTrue(ir["types"][0]["fields"][3]["omit_empty"])
            self.assertTrue(ir["types"][0]["fields"][4]["nullable"])
            self.assertEqual(ir["types"][0]["fields"][5]["string_values"],
                             ["live", "trashed"])
            self.assertTrue(next(entry for entry in ir["types"]
                                 if entry["name"] == "Detail")["inline"])
            generated = self.run_inspect(
                root, "--header", "sample/api.hpp", "--namespace", "sample",
                "--", "-Iinclude",
            )
            self.assertEqual(generated.returncode, 0, generated.stderr)
            self.assertEqual(generated.stdout, result.stdout)

    def test_header_mode_rejects_invalid_registration_inputs(self):
        cases = (
            (("--header", "api.hpp"), "--header requires --namespace"),
            (("inspect.cpp", "--namespace", "sample"), "--namespace requires --header"),
            (("inspect.cpp", "--header", "api.hpp", "--namespace", "sample"),
             "exactly one inspection source"),
            (("--header", 'api.hpp"\n#error injected', "--namespace", "sample"),
             "invalid C++ header path"),
            (("--header", "api.hpp", "--namespace", "sample::bad-name"),
             "invalid C++ namespace"),
        )
        with tempfile.TemporaryDirectory() as directory:
            for arguments, message in cases:
                with self.subTest(arguments=arguments):
                    result = self.run_inspect(directory, *arguments)
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout, "")
                    self.assertIn(message, result.stderr)
                    self.assertNotIn("Traceback", result.stderr)

    def test_header_mode_accepts_nested_namespace(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "api.hpp").write_text(
                '#include <rig/route.hpp>\n'
                'namespace sample::nested {\n'
                'struct Item { int value; };\n'
                'RIG_ROUTE(GET, "/items") Item get_item();\n'
                '}\n'
            )
            result = self.run_inspect(
                directory, "--header", "api.hpp", "--namespace", "sample::nested"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["operations"][0]["name"], "get_item")

    def test_header_mode_combines_namespaces_without_duplicate_types_or_operations(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "api.hpp").write_text(
                '#include <rig/route.hpp>\n'
                'namespace common { struct Item { int value; }; }\n'
                'namespace first {\n'
                'RIG_ROUTE(GET, "/first") common::Item read();\n'
                '}\n'
                'namespace second {\n'
                'RIG_ROUTE(GET, "/second") common::Item read();\n'
                '}\n'
            )
            result = self.run_inspect(
                directory, "--header", "api.hpp", "--namespace", "first",
                "--namespace", "second", "--namespace", "first",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            ir = json.loads(result.stdout)
            self.assertEqual([entry["cpp_name"] for entry in ir["types"]], ["common::Item"])
            self.assertEqual(
                [entry["cpp_name"] for entry in ir["operations"]],
                ["first::read", "second::read"],
            )

    def test_result_return_declares_success_and_error_bodies(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "api.hpp").write_text(
                '#include <rig/route.hpp>\n'
                '#include <rig/result.hpp>\n'
                'namespace sample {\n'
                'struct Item { int value; };\n'
                'struct Failure { int code; };\n'
                'using Reply = rig::result<Item, rig::error<404, Failure>>;\n'
                'RIG_ROUTE(GET, "/item") Reply get_item();\n'
                '}\n'
            )
            result = self.run_inspect(directory, "--header", "api.hpp", "--namespace", "sample")
            self.assertEqual(result.returncode, 0, result.stderr)
            ir = json.loads(result.stdout)
            self.assertEqual([entry["name"] for entry in ir["types"]], ["Item", "Failure"])
            operation = ir["operations"][0]
            self.assertEqual(operation["returns"], {"kind": "named", "name": "sample::Item"})
            self.assertEqual(operation["errors"], [{
                "status": 404, "type": {"kind": "named", "name": "sample::Failure"},
            }])

    def test_reflects_operation_text_and_boolean_field_value(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "api.hpp").write_text(
                '#include <rig/route.hpp>\n'
                'namespace sample {\n'
                'struct RIG_API("Example API", "0.2.0") RIG_SERVER("/") '
                'RIG_SERVER("http://127.0.0.1:9000") '
                'RIG_BEARER_AUTH("bearerAuth", "token") Service {};\n'
                'struct RIG_OPEN_RECORD Reply { bool ok RIG_BOOL_VALUE(true); };\n'
                'struct Error { bool ok RIG_BOOL_VALUE(false); };\n'
                'RIG_ROUTE(POST, "/bye")\n'
                'RIG_SUMMARY("Leaving")\n'
                'RIG_DESCRIPTION("A hint to the server.")\n'
                'RIG_RESPONSE_DESCRIPTION("Acknowledged")\n'
                'RIG_ERROR_RESPONSE(401, Error, "Unauthorized")\n'
                'Reply bye();\n'
                '}\n'
            )
            result = self.run_inspect(directory, "--header", "api.hpp", "--namespace", "sample")
            self.assertEqual(result.returncode, 0, result.stderr)
            ir = json.loads(result.stdout)
            self.assertEqual(ir["service"], {
                "title": "Example API", "version": "0.2.0",
                "servers": ["/", "http://127.0.0.1:9000"],
                "bearer_auth": {"name": "bearerAuth", "format": "token"},
            })
            self.assertEqual(ir["types"][0]["fields"][0]["bool_value"], True)
            self.assertTrue(ir["types"][0]["open"])
            operation = ir["operations"][0]
            self.assertEqual(operation["summary"], "Leaving")
            self.assertEqual(operation["description"], "A hint to the server.")
            self.assertEqual(operation["response_description"], "Acknowledged")
            self.assertEqual(operation["errors"], [{
                "status": 401, "type": {"kind": "named", "name": "sample::Error"},
                "description": "Unauthorized",
            }])
            self.assertEqual([entry["name"] for entry in ir["types"]], ["Reply", "Error"])
            codec = subprocess.run(
                [sys.executable, "-m", "rig", "json-codec", "--api-header", "api.hpp"],
                input=result.stdout, cwd=directory, text=True, capture_output=True,
            )
            self.assertEqual(codec.returncode, 0, codec.stderr)
            (Path(directory) / "codec.hpp").write_text(codec.stdout)
            (Path(directory) / "check.cpp").write_text(
                '#include "codec.hpp"\n'
                'int main() {\n'
                '  auto value = rig_json::decode<sample::Reply>('
                'nlohmann::json{{"ok", true}, {"extra", 1}});\n'
                '  if (!value.ok) return 1;\n'
                '  try { (void)rig_json::decode<sample::Reply>('
                'nlohmann::json{{"ok", false}}); return 2; }\n'
                '  catch (const std::invalid_argument&) {}\n'
                '  try { (void)rig_json::encode(sample::Reply{false}); return 3; }\n'
                '  catch (const std::invalid_argument&) {}\n'
                '}\n'
            )
            include_dir = Path(__file__).resolve().parents[1] / "src" / "rig" / "include"
            binary = Path(directory) / "check"
            compiled = subprocess.run(
                ["g++", "-std=c++20", f"-I{include_dir}", "-I.", "check.cpp", "-o", str(binary)],
                cwd=directory, text=True, capture_output=True,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            run = subprocess.run([binary], cwd=directory, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_error_responses_map_exception_types(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "api.hpp").write_text(
                '#include <rig/route.hpp>\n'
                '#include <stdexcept>\n'
                'namespace sample {\n'
                'struct Item { int value; };\n'
                'struct Error { int code; };\n'
                'struct Missing : std::runtime_error { using std::runtime_error::runtime_error; };\n'
                'RIG_ROUTE(GET, "/item")\n'
                'RIG_ERROR_RESPONSE(401, Error, "Unauthorized")\n'
                'RIG_ERROR_RESPONSE(404, Error, "Not found", Missing, std::out_of_range)\n'
                'RIG_ERROR_RESPONSE(500, Error, "Failed", std::exception)\n'
                'Item get_item();\n'
                '}\n'
            )
            result = self.run_inspect(directory, "--header", "api.hpp", "--namespace", "sample")
            self.assertEqual(result.returncode, 0, result.stderr)
            errors = json.loads(result.stdout)["operations"][0]["errors"]
            self.assertEqual([error.get("exceptions") for error in errors], [
                None, ["sample::Missing", "std::out_of_range"], ["std::exception"],
            ])

    def test_error_responses_reject_shadowed_exception_types(self):
        cases = (
            'RIG_ERROR_RESPONSE(500, Error, "Failed", std::exception)\n'
            'RIG_ERROR_RESPONSE(404, Error, "Not found", Missing)\n',
            'RIG_ERROR_RESPONSE(404, Error, "Not found", Missing)\n'
            'RIG_ERROR_RESPONSE(410, Error, "Gone", Missing)\n',
        )
        for annotations in cases:
            with self.subTest(annotations=annotations), \
                    tempfile.TemporaryDirectory() as directory:
                (Path(directory) / "api.hpp").write_text(
                    '#include <rig/route.hpp>\n'
                    '#include <stdexcept>\n'
                    'namespace sample {\n'
                    'struct Item { int value; };\n'
                    'struct Error { int code; };\n'
                    'struct Missing : std::runtime_error { using std::runtime_error::runtime_error; };\n'
                    'RIG_ROUTE(GET, "/item")\n' + annotations +
                    'Item get_item();\n'
                    '}\n'
                )
                result = self.run_inspect(directory, "--header", "api.hpp",
                                          "--namespace", "sample")
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertIn("listed derived before base", result.stderr)

    def test_compilation_failure_has_no_ir_output(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "bad.cpp").write_text("int main( {\n")
            result = self.run_inspect(directory, "bad.cpp")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertIn("C++ inspection compilation failed", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_invalid_inspector_output_has_no_ir_output(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "invalid.cpp").write_text(
                '#include <iostream>\nint main() { std::cout << "{}"; }\n'
            )
            result = self.run_inspect(directory, "invalid.cpp")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertIn("missing ir_version", result.stderr)


if __name__ == "__main__":
    unittest.main()
