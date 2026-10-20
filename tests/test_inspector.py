"""The installed command owns C++26 compilation and validates its output."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class InspectorTests(unittest.TestCase):
    def run_inspect(self, directory, *arguments):
        return subprocess.run(
            [sys.executable, "-m", "rig", "inspect", *arguments],
            cwd=directory, text=True, capture_output=True,
        )

    def test_compiles_with_forwarded_include_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            header = root / "include" / "sample" / "api.hpp"
            header.parent.mkdir(parents=True)
            header.write_text(
                '#include <rig/route.hpp>\n'
                'namespace sample {\n'
                'struct Item { int value; };\n'
                'RIG_ROUTE(GET, "/items/{id}") Item get_item(int id);\n'
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
            self.assertEqual(ir["ir_version"], 2)
            self.assertEqual(ir["operations"][0]["path"], "/items/{id}")
            self.assertEqual(ir["types"][0]["fields"][0]["name"], "value")
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
