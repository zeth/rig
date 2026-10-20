"""Exercise the installed command interface used by external projects."""

import json
import subprocess
import sys
import unittest
from pathlib import Path


class CommandTests(unittest.TestCase):
    def run_rig(self, *arguments, input_text=None):
        return subprocess.run(
            [sys.executable, "-m", "rig", *arguments], input=input_text,
            text=True, capture_output=True, check=True,
        ).stdout

    def test_include_dir_contains_public_headers(self):
        include_dir = Path(self.run_rig("include-dir").strip())
        self.assertTrue((include_dir / "rig" / "route.hpp").is_file())
        self.assertTrue((include_dir / "rig" / "inspect.hpp").is_file())
        self.assertTrue((include_dir / "rig" / "result.hpp").is_file())

    def test_openapi_and_embedding_use_standard_streams(self):
        ir = {"ir_version": 5, "types": [], "operations": []}
        self.assertEqual(self.run_rig("validate", input_text=json.dumps(ir)), "")
        document = self.run_rig("openapi", "--title", "Test", input_text=json.dumps(ir))
        self.assertEqual(json.loads(document)["info"]["title"], "Test")
        header = self.run_rig("embed-openapi", input_text=document)
        self.assertIn(f"openapi_json{{openapi_bytes, {len(document.encode())}}}", header)

    def test_validate_reports_location_without_traceback(self):
        ir = {"ir_version": 5, "types": [], "operations": [{}]}
        result = subprocess.run(
            [sys.executable, "-m", "rig", "validate"], input=json.dumps(ir),
            text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("$.operations[0]", result.stderr)
        self.assertIn("missing", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
