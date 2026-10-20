"""Compile and run a C++26 reflection entry point."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from .ir import identifier, validate


def _registration_source(header, namespace):
    if not isinstance(header, str) or not header or any(
        ord(character) < 32 or character in ('"', '\\') for character in header
    ):
        raise ValueError(f"invalid C++ header path: {header!r}")
    if not isinstance(namespace, str):
        raise ValueError(f"invalid C++ namespace: {namespace!r}")
    try:
        parts = [identifier(part) for part in namespace.split("::")]
    except ValueError:
        raise ValueError(f"invalid C++ namespace: {namespace!r}") from None
    return (
        f'#include "{header}"\n'
        '#include <rig/inspect.hpp>\n'
        '#include <iostream>\n'
        'int main() {\n'
        '    rig::writer output(std::cout);\n'
        f'    output.add_namespace<^^{"::".join(parts)}>();\n'
        '    output.finish();\n'
        '}\n'
    )


def inspect(source=None, cxx="g++", compiler_flags=(), *, header=None, namespace=None):
    """Return validated IR bytes from an entry point or C++20 header."""
    if (source is None) == (header is None):
        raise ValueError("provide exactly one inspection source or --header")
    if header is None and namespace is not None:
        raise ValueError("--namespace requires --header")
    if header is not None and namespace is None:
        raise ValueError("--header requires --namespace")
    registration = _registration_source(header, namespace) if header is not None else None
    include_dir = Path(__file__).resolve().parent / "include"
    with tempfile.TemporaryDirectory(prefix="rig-inspect-") as directory:
        executable = Path(directory) / "inspector"
        if registration is not None:
            source = Path(directory) / "registration.cpp"
            source.write_text(registration)
            compiler_flags = (f"-I{Path.cwd()}", *compiler_flags)
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
