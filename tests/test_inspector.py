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
                'struct RIG_OPEN_RECORD Reply { bool ok RIG_BOOL_VALUE(true); };\n'
                'struct Error { bool ok RIG_BOOL_VALUE(false); };\n'
                'struct RIG_API("Example API", "0.2.0") RIG_SERVER("/") '
                'RIG_SERVER("http://127.0.0.1:9000") '
                'RIG_BEARER_AUTH("bearerAuth", "token") '
                'RIG_UNAUTHORIZED(Error, "Unauthorized") Service {};\n'
                'RIG_ROUTE(POST, "/bye")\n'
                'RIG_SUMMARY("Leaving")\n'
                'RIG_DESCRIPTION("A hint to the server.")\n'
                'RIG_RESPONSE_DESCRIPTION("Acknowledged")\n'
                'Reply bye();\n'
                'RIG_ROUTE(GET, "/ping") RIG_PUBLIC Reply ping();\n'
                '}\n'
            )
            result = self.run_inspect(directory, "--header", "api.hpp", "--namespace", "sample")
            self.assertEqual(result.returncode, 0, result.stderr)
            ir = json.loads(result.stdout)
            self.assertEqual(ir["service"], {
                "title": "Example API", "version": "0.2.0",
                "servers": ["/", "http://127.0.0.1:9000"],
                "bearer_auth": {"name": "bearerAuth", "format": "token"},
                "unauthorized": {"type": {"kind": "named", "name": "sample::Error"},
                                 "description": "Unauthorized"},
            })
            self.assertEqual(ir["types"][0]["fields"][0]["bool_value"], True)
            self.assertTrue(ir["types"][0]["open"])
            operation = ir["operations"][0]
            self.assertEqual(operation["summary"], "Leaving")
            self.assertEqual(operation["description"], "A hint to the server.")
            self.assertEqual(operation["response_description"], "Acknowledged")
            self.assertEqual(operation["errors"], [])
            self.assertNotIn("public", operation)
            self.assertIs(ir["operations"][1]["public"], True)
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

    def test_validation_error_body_is_built_by_the_application(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "api.hpp").write_text(
                '#include <rig/route.hpp>\n'
                '#include <exception>\n#include <string>\n#include <type_traits>\n'
                'namespace sample {\n'
                'struct Failure { bool ok RIG_BOOL_VALUE(false); std::string message; };\n'
                'struct RIG_API("Sample", "1.0") RIG_BEARER_AUTH("bearerAuth", "token") '
                'RIG_VALIDATION_ERROR(Failure, "Bad request") '
                'RIG_INTERNAL_ERROR(Failure, "Internal server error") Service {};\n'
                'struct Item { std::string name; int count; };\n'
                'RIG_ROUTE(PUT, "/items/{id}") Item put_item(int id, Item item);\n'
                'RIG_ROUTE(GET, "/items/{name}") RIG_PUBLIC Item read_item(std::string name);\n'
                'RIG_ROUTE(GET, "/items/new") Item new_item();\n'
                '// Declared for the contract only; the host serves it and nothing defines it.\n'
                'RIG_ROUTE(GET, "/items/{name}/raw") RIG_PUBLIC '
                'RIG_HOST_RESPONSE("text/plain") std::string raw_item(std::string name);\n'
                'Failure rig_error_body(std::type_identity<Failure>, int status, '
                'const std::exception& error);\n'
                '}\n'
            )
            result = self.run_inspect(directory, "--header", "api.hpp", "--namespace", "sample")
            self.assertEqual(result.returncode, 0, result.stderr)
            ir = json.loads(result.stdout)
            self.assertEqual(ir["service"]["validation_error"], {
                "type": {"kind": "named", "name": "sample::Failure"},
                "description": "Bad request",
            })
            self.assertIn("sample::Failure", [entry["cpp_name"] for entry in ir["types"]])
            self.assertEqual(ir["service"]["internal_error"]["description"],
                             "Internal server error")
            self.assertEqual([operation.get("public", False) for operation in ir["operations"]],
                             [False, True, False, True])
            self.assertEqual(ir["operations"][3]["host_response"], "text/plain")
            for command, flag, output in (("json-codec", "--api-header", "codec.hpp"),
                                          ("http-routes", "--codec-header", "routes.hpp")):
                generated = subprocess.run(
                    [sys.executable, "-m", "rig", command, flag,
                     "api.hpp" if command == "json-codec" else "codec.hpp"],
                    input=result.stdout, cwd=directory, text=True, capture_output=True,
                )
                self.assertEqual(generated.returncode, 0, generated.stderr)
                (root / output).write_text(generated.stdout)
            (root / "check.cpp").write_text(
                '#include "routes.hpp"\n'
                'sample::Item sample::put_item(int, Item item) {\n'
                '  if (item.count < 0) throw std::logic_error("negative count");\n'
                '  return item;\n'
                '}\n'
                'sample::Item sample::read_item(std::string name) { return {name, 1}; }\n'
                'sample::Item sample::new_item() { return {"new", 0}; }\n'
                'sample::Failure sample::rig_error_body(std::type_identity<Failure>, int status, '
                'const std::exception& error) {\n'
                '  return {false, std::to_string(status) + ": " + error.what()};\n'
                '}\n'
                'int main() {\n'
                '  auto ok = rig_http::dispatch("PUT", "/items/1", R"({"name":"a","count":1})");\n'
                '  if (!ok || ok->status != 200) return 1;\n'
                '  auto missing = rig_http::dispatch("PUT", "/items/1", R"({"name":"a"})");\n'
                '  if (!missing || missing->status != 400 || missing->body["ok"] != false ||\n'
                '      missing->body["message"] != "400: missing count") return 2;\n'
                '  auto path = rig_http::dispatch("PUT", "/items/99999999999", "{}");\n'
                '  if (!path || path->status != 400 || path->body.contains("code")) return 3;\n'
                '  auto failed = rig_http::dispatch("PUT", "/items/1", R"({"name":"a","count":-1})");\n'
                '  if (!failed || failed->status != 500 ||\n'
                '      failed->body["message"] != "500: negative count") return 4;\n'
                '  if (!rig_http::is_public("GET", "/items/a?view=1")) return 5;\n'
                '  if (rig_http::is_public("GET", "/items/new")) return 6;\n'
                '  if (rig_http::is_public("PUT", "/items/1")) return 7;\n'
                '  if (rig_http::is_public("GET", "/elsewhere")) return 8;\n'
                '  if (rig_http::dispatch("GET", "/items/a/raw", "")) return 9;\n'
                '  if (!rig_http::is_public("GET", "/items/a/raw")) return 10;\n'
                '}\n'
            )
            include_dir = Path(__file__).resolve().parents[1] / "src" / "rig" / "include"
            binary = root / "check"
            compiled = subprocess.run(
                ["g++", "-std=c++20", "-Wall", "-Wextra", "-Werror", f"-I{include_dir}", "-I.",
                 "check.cpp", "-o", str(binary)],
                cwd=directory, text=True, capture_output=True,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            run = subprocess.run([binary], cwd=directory, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_free_form_objects_maps_and_success_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "api.hpp").write_text(
                '#include <rig/route.hpp>\n'
                '#include <nlohmann/json.hpp>\n'
                '#include <map>\n#include <optional>\n#include <string>\n#include <vector>\n'
                'namespace sample {\n'
                'struct Item {\n'
                '  nlohmann::json context;\n'
                '  std::optional<nlohmann::json> trace RIG_NULLABLE;\n'
                '  std::map<std::string, std::vector<std::string>> metadata;\n'
                '  std::map<std::string, std::string> secrets RIG_WRITE_ONLY;\n'
                '};\n'
                'RIG_ROUTE(POST, "/items") RIG_SUCCESS_STATUS(201) Item create_item(Item item);\n'
                '}\n'
            )
            result = self.run_inspect(directory, "--header", "api.hpp", "--namespace", "sample")
            self.assertEqual(result.returncode, 0, result.stderr)
            ir = json.loads(result.stdout)
            self.assertEqual([entry["cpp_name"] for entry in ir["types"]], ["sample::Item"])
            fields = ir["types"][0]["fields"]
            self.assertEqual(fields[0]["type"], {"kind": "builtin", "name": "object"})
            self.assertEqual(fields[2]["type"], {"kind": "map", "values": {
                "kind": "array", "items": {"kind": "builtin", "name": "string"}}})
            self.assertEqual(ir["operations"][0]["success_status"], 201)
            self.assertIs(fields[3]["write_only"], True)
            for command, flag, output in (("json-codec", "--api-header", "codec.hpp"),
                                          ("http-routes", "--codec-header", "routes.hpp")):
                generated = subprocess.run(
                    [sys.executable, "-m", "rig", command, flag,
                     "api.hpp" if command == "json-codec" else "codec.hpp"],
                    input=result.stdout, cwd=directory, text=True, capture_output=True,
                )
                self.assertEqual(generated.returncode, 0, generated.stderr)
                (root / output).write_text(generated.stdout)
            (root / "check.cpp").write_text(
                '#include "routes.hpp"\n'
                'sample::Item sample::create_item(Item item) { return item; }\n'
                'int main() {\n'
                '  auto created = rig_http::dispatch("POST", "/items",\n'
                '      R"({"context":{"a":[1]},"trace":null,"metadata":{"k":["v"]},"secrets":{}})");\n'
                '  if (!created || created->status != 201) return 1;\n'
                '  if (created->body["context"]["a"][0] != 1 || !created->body["trace"].is_null() ||\n'
                '      created->body["metadata"]["k"][0] != "v") return 2;\n'
                '  auto not_object = rig_http::dispatch("POST", "/items",\n'
                '      R"({"context":[1],"trace":null,"metadata":{},"secrets":{}})");\n'
                '  if (!not_object || not_object->status != 400) return 3;\n'
                '  auto bad_map = rig_http::dispatch("POST", "/items",\n'
                '      R"({"context":{},"trace":null,"metadata":{"k":"v"},"secrets":{}})");\n'
                '  if (!bad_map || bad_map->status != 400) return 4;\n'
                '}\n'
            )
            include_dir = Path(__file__).resolve().parents[1] / "src" / "rig" / "include"
            binary = root / "check"
            compiled = subprocess.run(
                ["g++", "-std=c++20", "-Wall", "-Wextra", "-Werror", f"-I{include_dir}", "-I.",
                 "check.cpp", "-o", str(binary)],
                cwd=directory, text=True, capture_output=True,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            run = subprocess.run([binary], cwd=directory, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_formats_lengths_defaults_choices_and_optional_bodies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "api.hpp").write_text(
                '#include <rig/route.hpp>\n'
                '#include <optional>\n#include <string>\n'
                'namespace sample {\n'
                'struct RIG_DESCRIPTION("A label on items.") Tag {\n'
                '  std::string id RIG_FORMAT("uuid");\n'
                '  std::string name RIG_MIN_LENGTH(1) RIG_MAX_LENGTH(8);\n'
                '  bool pinned RIG_DEFAULT(false);\n'
                '};\n'
                'RIG_ROUTE(GET, "/tags") Tag list_tags(\n'
                '    int limit RIG_QUERY RIG_RANGE(1, 50) RIG_DEFAULT(20),\n'
                '    std::string order RIG_QUERY RIG_STRING_VALUES("name", "recent") RIG_DEFAULT("name"),\n'
                '    std::optional<int> offset RIG_QUERY RIG_MINIMUM(0) RIG_FORMAT("int32"),\n'
                '    std::optional<std::string> prefix RIG_QUERY RIG_MIN_LENGTH(1));\n'
                'RIG_ROUTE(GET, "/tags/since") Tag tags_since(long long after RIG_QUERY);\n'
                'RIG_ROUTE(DELETE, "/tags/{name}") Tag delete_tag(std::string name,\n'
                '                                                 std::optional<Tag> replacement);\n'
                '}\n'
            )
            result = self.run_inspect(directory, "--header", "api.hpp", "--namespace", "sample")
            self.assertEqual(result.returncode, 0, result.stderr)
            ir = json.loads(result.stdout)
            fields = ir["types"][0]["fields"]
            self.assertEqual(fields[0]["format"], "uuid")
            self.assertEqual((fields[1]["min_length"], fields[1]["max_length"]), (1, 8))
            self.assertIs(fields[2]["default"], False)
            limit, order, offset, prefix = ir["operations"][0]["parameters"]
            self.assertEqual(limit["default"], 20)
            self.assertEqual((order["string_values"], order["default"]), (["name", "recent"], "name"))
            self.assertEqual((offset["minimum"], offset["format"]), (0, "int32"))
            self.assertEqual(prefix["min_length"], 1)
            document = subprocess.run(
                [sys.executable, "-m", "rig", "openapi"], input=result.stdout, cwd=directory,
                text=True, capture_output=True,
            )
            self.assertEqual(document.returncode, 0, document.stderr)
            openapi = json.loads(document.stdout)
            tag = openapi["components"]["schemas"]["Tag"]
            self.assertEqual(tag["description"], "A label on items.")
            self.assertEqual(openapi["paths"]["/tags/since"]["get"]["parameters"][0]["schema"],
                             {"type": "integer", "format": "int64"})
            self.assertEqual(tag["required"], ["id", "name"])
            self.assertEqual(tag["properties"]["pinned"], {"type": "boolean", "default": False})
            self.assertEqual(tag["properties"]["name"],
                             {"type": "string", "minLength": 1, "maxLength": 8})
            query = openapi["paths"]["/tags"]["get"]["parameters"]
            self.assertEqual(query[0], {"name": "limit", "in": "query", "required": False,
                                        "schema": {"type": "integer", "minimum": 1,
                                                   "maximum": 50, "default": 20}})
            self.assertEqual(query[1]["schema"], {"type": "string", "enum": ["name", "recent"],
                                                  "default": "name"})
            self.assertEqual(query[2]["schema"],
                             {"type": "integer", "minimum": 0, "format": "int32"})
            self.assertIs(openapi["paths"]["/tags/{name}"]["delete"]["requestBody"]["required"],
                          False)
            for command, flag, output in (("json-codec", "--api-header", "codec.hpp"),
                                          ("http-routes", "--codec-header", "routes.hpp")):
                generated = subprocess.run(
                    [sys.executable, "-m", "rig", command, flag,
                     "api.hpp" if command == "json-codec" else "codec.hpp"],
                    input=result.stdout, cwd=directory, text=True, capture_output=True,
                )
                self.assertEqual(generated.returncode, 0, generated.stderr)
                (root / output).write_text(generated.stdout)
            (root / "check.cpp").write_text(
                '#include "routes.hpp"\n'
                'sample::Tag sample::list_tags(int limit, std::string order, std::optional<int> offset,\n'
                '                              std::optional<std::string>) {\n'
                '  return {std::to_string(offset.value_or(-1)), order, limit == 20};\n'
                '}\n'
                'sample::Tag sample::tags_since(long long after) { return {std::to_string(after), "", false}; }\n'
                'sample::Tag sample::delete_tag(std::string name, std::optional<Tag> replacement) {\n'
                '  return replacement ? *replacement : Tag{"none", name, false};\n'
                '}\n'
                'int status(const char* method, const char* path, const char* body = "") {\n'
                '  const auto response = rig_http::dispatch(method, path, body);\n'
                '  return response ? response->status : 0;\n'
                '}\n'
                'int main() {\n'
                '  auto defaults = rig_http::dispatch("GET", "/tags", "");\n'
                '  if (!defaults || defaults->body["name"] != "name" || defaults->body["pinned"] != true ||\n'
                '      defaults->body["id"] != "-1") return 1;\n'
                '  if (status("GET", "/tags?order=recent&offset=0&limit=50") != 200) return 2;\n'
                '  if (status("GET", "/tags?order=size") != 400) return 3;\n'
                '  if (status("GET", "/tags?offset=-1") != 400) return 4;\n'
                '  if (status("GET", "/tags?prefix=") != 400) return 5;\n'
                '  if (status("GET", "/tags?limit=51") != 400) return 6;\n'
                '  auto empty = rig_http::dispatch("DELETE", "/tags/old", "");\n'
                '  if (!empty || empty->body["id"] != "none") return 7;\n'
                '  auto replaced = rig_http::dispatch("DELETE", "/tags/old", R"({"id":"u","name":"new"})");\n'
                '  if (!replaced || replaced->body["name"] != "new" || replaced->body["pinned"] != false)\n'
                '    return 8;\n'
                '  if (status("DELETE", "/tags/old", R"({"id":"u","name":""})") != 400) return 9;\n'
                '  if (status("DELETE", "/tags/old", R"({"id":"u","name":"far too long"})") != 400)\n'
                '    return 10;\n'
                '  auto since = rig_http::dispatch("GET", "/tags/since?after=9000000000", "");\n'
                '  if (!since || since->body["id"] != "9000000000") return 11;\n'
                '  if (status("GET", "/tags/since?after=soon") != 400) return 12;\n'
                '}\n'
            )
            include_dir = Path(__file__).resolve().parents[1] / "src" / "rig" / "include"
            binary = root / "check"
            compiled = subprocess.run(
                ["g++", "-std=c++20", "-Wall", "-Wextra", "-Werror", f"-I{include_dir}", "-I.",
                 "check.cpp", "-o", str(binary)],
                cwd=directory, text=True, capture_output=True,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            run = subprocess.run([binary], cwd=directory, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_value_types_inheritance_and_patterns(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "api.hpp").write_text(
                '#include <rig/route.hpp>\n'
                '#include <map>\n#include <optional>\n#include <string>\n#include <vector>\n'
                'namespace sample {\n'
                'struct RIG_VALUE_TYPE RIG_DESCRIPTION("A commit ID or prefix.") Revision {\n'
                '  std::string value RIG_MIN_LENGTH(4) RIG_MAX_LENGTH(8) RIG_PATTERN("^[0-9a-f]+$");\n'
                '};\n'
                'struct RIG_VALUE_TYPE RIG_DESCRIPTION("Labels.") Labels {\n'
                '  std::map<std::string, std::vector<std::string>> value;\n'
                '};\n'
                'struct Item { std::string id; Labels labels; };\n'
                'struct RIG_OPEN_RECORD DetailedItem : Item {\n'
                '  std::optional<std::string> note RIG_OMIT_EMPTY RIG_PATTERN("^n");\n'
                '};\n'
                'RIG_ROUTE(GET, "/items") DetailedItem item_at(Revision at RIG_QUERY);\n'
                'RIG_ROUTE(PUT, "/items") DetailedItem put_item(DetailedItem item);\n'
                '}\n'
            )
            result = self.run_inspect(directory, "--header", "api.hpp", "--namespace", "sample")
            self.assertEqual(result.returncode, 0, result.stderr)
            ir = json.loads(result.stdout)
            types = {entry["name"]: entry for entry in ir["types"]}
            self.assertIs(types["Revision"]["value"], True)
            self.assertEqual(types["DetailedItem"]["base"], "sample::Item")
            self.assertEqual([field["name"] for field in types["DetailedItem"]["fields"]], ["note"])
            document = subprocess.run(
                [sys.executable, "-m", "rig", "openapi"], input=result.stdout, cwd=directory,
                text=True, capture_output=True,
            )
            self.assertEqual(document.returncode, 0, document.stderr)
            schemas = json.loads(document.stdout)["components"]["schemas"]
            self.assertEqual(schemas["Revision"], {
                "type": "string", "minLength": 4, "maxLength": 8, "pattern": "^[0-9a-f]+$",
                "description": "A commit ID or prefix.",
            })
            self.assertEqual(schemas["Labels"], {
                "type": "object", "description": "Labels.",
                "additionalProperties": {"type": "array", "items": {"type": "string"}},
            })
            self.assertEqual(schemas["DetailedItem"], {"allOf": [
                {"$ref": "#/components/schemas/Item"},
                {"type": "object", "properties": {"note": {"type": "string", "pattern": "^n"}}},
            ]})
            self.assertEqual(schemas["Item"]["properties"]["labels"],
                             {"$ref": "#/components/schemas/Labels"})
            for command, flag, output in (("json-codec", "--api-header", "codec.hpp"),
                                          ("http-routes", "--codec-header", "routes.hpp")):
                generated = subprocess.run(
                    [sys.executable, "-m", "rig", command, flag,
                     "api.hpp" if command == "json-codec" else "codec.hpp"],
                    input=result.stdout, cwd=directory, text=True, capture_output=True,
                )
                self.assertEqual(generated.returncode, 0, generated.stderr)
                (root / output).write_text(generated.stdout)
            (root / "check.cpp").write_text(
                '#include "routes.hpp"\n'
                'sample::DetailedItem sample::item_at(Revision at) {\n'
                '  return {{at.value, {{{"k", {"v"}}}}}, std::nullopt};\n'
                '}\n'
                'sample::DetailedItem sample::put_item(DetailedItem item) { return item; }\n'
                'int status(const char* method, const char* path, const char* body = "") {\n'
                '  const auto response = rig_http::dispatch(method, path, body);\n'
                '  return response ? response->status : 0;\n'
                '}\n'
                'int main() {\n'
                '  auto found = rig_http::dispatch("GET", "/items?at=abc1", "");\n'
                '  if (!found || found->status != 200 || found->body["id"] != "abc1" ||\n'
                '      found->body["labels"]["k"][0] != "v" || found->body.contains("note")) return 1;\n'
                '  if (status("GET", "/items?at=abc") != 400) return 2;\n'
                '  if (status("GET", "/items?at=ABCD") != 400) return 3;\n'
                '  auto put = rig_http::dispatch("PUT", "/items",\n'
                '      R"({"id":"x","labels":{},"note":"nice"})");\n'
                '  if (!put || put->status != 200 || put->body["note"] != "nice") return 4;\n'
                '  if (status("PUT", "/items", R"({"id":"x","labels":{},"note":"bad"})") != 400) return 5;\n'
                '  if (status("PUT", "/items", R"({"labels":{},"note":"nice"})") != 400) return 6;\n'
                '  if (status("PUT", "/items", R"({"id":"x","labels":{},"extra":1})") != 400) return 7;\n'
                '}\n'
            )
            include_dir = Path(__file__).resolve().parents[1] / "src" / "rig" / "include"
            binary = root / "check"
            compiled = subprocess.run(
                ["g++", "-std=c++20", "-Wall", "-Wextra", "-Werror", f"-I{include_dir}", "-I.",
                 "check.cpp", "-o", str(binary)],
                cwd=directory, text=True, capture_output=True,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            run = subprocess.run([binary], cwd=directory, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_nullable_choices_records_and_host_response_details(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "api.hpp").write_text(
                '#include <rig/route.hpp>\n'
                '#include <optional>\n#include <string>\n'
                'namespace sample {\n'
                'struct RIG_API("Sample", "1.0") RIG_BEARER_AUTH("bearerAuth", "token") Service {};\n'
                'struct Info { std::string name; };\n'
                'struct RIG_MIN_PROPERTIES(1) Update {\n'
                '  std::optional<std::optional<std::string>> mode RIG_OMIT_EMPTY RIG_NULLABLE\n'
                '      RIG_STRING_VALUES("plain", "encrypted");\n'
                '  std::optional<std::string> status RIG_NULLABLE RIG_STRING_VALUES("ok", "failed");\n'
                '  std::optional<std::optional<Info>> info RIG_OMIT_EMPTY RIG_NULLABLE;\n'
                '};\n'
                'RIG_ROUTE(PATCH, "/update") Update apply(Update update);\n'
                'RIG_ROUTE(GET, "/ping") RIG_PUBLIC RIG_HOST_RESPONSE("text/plain")\n'
                '    RIG_STRING_VALUES("pong") std::string ping();\n'
                'RIG_ROUTE(GET, "/blob") RIG_HOST_RESPONSE("application/octet-stream")\n'
                '    RIG_FORMAT("binary") RIG_OPERATION_ID("download_blob") std::string blob();\n'
                'RIG_ROUTE(POST, "/import") RIG_HOST_RESPONSE("application/json")\n'
                '    RIG_RESPONSE_DESCRIPTION("Matched") RIG_SUCCESS_RESPONSE(201, "Created")\n'
                '    Info import_info(Info info);\n'
                '}\n'
            )
            result = self.run_inspect(directory, "--header", "api.hpp", "--namespace", "sample")
            self.assertEqual(result.returncode, 0, result.stderr)
            document = subprocess.run(
                [sys.executable, "-m", "rig", "openapi", "--omit-operation-ids"],
                input=result.stdout, cwd=directory, text=True, capture_output=True,
            )
            self.assertEqual(document.returncode, 0, document.stderr)
            openapi = json.loads(document.stdout)
            update = openapi["components"]["schemas"]["Update"]
            self.assertEqual(update["minProperties"], 1)
            self.assertEqual(update["required"], ["status"])
            self.assertEqual(update["properties"]["mode"],
                             {"type": ["string", "null"], "enum": ["plain", "encrypted", None]})
            self.assertEqual(update["properties"]["info"], {"anyOf": [
                {"$ref": "#/components/schemas/Info"}, {"type": "null"}]})
            paths = openapi["paths"]
            self.assertEqual(paths["/ping"]["get"]["responses"]["200"]["content"],
                             {"text/plain": {"schema": {"type": "string", "enum": ["pong"]}}})
            self.assertEqual(paths["/blob"]["get"]["operationId"], "download_blob")
            self.assertNotIn("operationId", paths["/ping"]["get"])
            self.assertEqual(
                paths["/blob"]["get"]["responses"]["200"]["content"]["application/octet-stream"],
                {"schema": {"type": "string", "format": "binary"}})
            imported = paths["/import"]["post"]["responses"]
            self.assertEqual((imported["200"]["description"], imported["201"]["description"]),
                             ("Matched", "Created"))
            self.assertEqual(imported["201"]["content"], imported["200"]["content"])
            for command, flag, output in (("json-codec", "--api-header", "codec.hpp"),
                                          ("http-routes", "--codec-header", "routes.hpp")):
                generated = subprocess.run(
                    [sys.executable, "-m", "rig", command, flag,
                     "api.hpp" if command == "json-codec" else "codec.hpp"],
                    input=result.stdout, cwd=directory, text=True, capture_output=True,
                )
                self.assertEqual(generated.returncode, 0, generated.stderr)
                (root / output).write_text(generated.stdout)
            (root / "check.cpp").write_text(
                '#include "routes.hpp"\n'
                'sample::Update sample::apply(Update update) { return update; }\n'
                'int status(const char* body) {\n'
                '  const auto response = rig_http::dispatch("PATCH", "/update", body);\n'
                '  return response ? response->status : 0;\n'
                '}\n'
                'int main() {\n'
                '  if (status(R"({"status":null})") != 200) return 1;\n'
                '  if (status(R"({"status":"ok","mode":null,"info":null})") != 200) return 2;\n'
                '  if (status(R"({"status":"ok","mode":"plain","info":{"name":"n"}})") != 200) return 3;\n'
                '  if (status(R"({"status":"maybe"})") != 400) return 4;\n'
                '  if (status(R"({"status":null,"mode":"open"})") != 400) return 5;\n'
                '  if (status("{}") != 400) return 6;\n'
                '  auto echoed = rig_http::dispatch("PATCH", "/update", R"({"status":null,"info":null})");\n'
                '  if (!echoed->body.contains("info") || !echoed->body["info"].is_null() ||\n'
                '      echoed->body.contains("mode")) return 7;\n'
                '  if (rig_http::dispatch("GET", "/ping", "")) return 8;\n'
                '}\n'
            )
            include_dir = Path(__file__).resolve().parents[1] / "src" / "rig" / "include"
            binary = root / "check"
            compiled = subprocess.run(
                ["g++", "-std=c++20", "-Wall", "-Wextra", "-Werror", f"-I{include_dir}", "-I.",
                 "check.cpp", "-o", str(binary)],
                cwd=directory, text=True, capture_output=True,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            run = subprocess.run([binary], cwd=directory, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_ordered_json_is_not_a_free_form_object(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "api.hpp").write_text(
                '#include <rig/route.hpp>\n#include <nlohmann/json.hpp>\n'
                'namespace sample { struct Item { nlohmann::ordered_json context; };\n'
                'RIG_ROUTE(GET, "/item") Item get_item(); }\n'
            )
            result = self.run_inspect(directory, "--header", "api.hpp", "--namespace", "sample")
            self.assertEqual(result.returncode, 1)
            self.assertIn("unsupported", result.stderr)

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
