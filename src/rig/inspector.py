"""Compile and run a C++26 reflection entry point."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from .ir import validate


def inspect(source, cxx="g++", compiler_flags=()):
    """Return validated IR bytes from a reflection entry point."""
    include_dir = Path(__file__).resolve().parent / "include"
    with tempfile.TemporaryDirectory(prefix="rig-inspect-") as directory:
        executable = Path(directory) / "inspector"
        command = [
            cxx, "-std=c++26", "-freflection", "-DRIG_GENERATING",
            f"-I{include_dir}", source, "-o", str(executable), *compiler_flags,
        ]
        try:
            compiler = subprocess.run(command, capture_output=True)
        except OSError as error:
            raise ValueError(f"cannot run C++ compiler {cxx!r}: {error}") from None
        if compiler.stdout:
            sys.stderr.buffer.write(compiler.stdout)
        if compiler.stderr:
            sys.stderr.buffer.write(compiler.stderr)
        if compiler.returncode:
            raise ValueError(f"C++ inspection compilation failed (exit {compiler.returncode})")
        try:
            result = subprocess.run([executable], stdout=subprocess.PIPE)
        except OSError as error:
            raise ValueError(f"cannot run compiled inspector: {error}") from None
        if result.returncode:
            raise ValueError(f"C++ inspector failed (exit {result.returncode})")
        try:
            document = json.loads(result.stdout)
        except (UnicodeError, ValueError) as error:
            raise ValueError(f"inspector output is invalid JSON: {error}") from None
        validate(document)
        return result.stdout
