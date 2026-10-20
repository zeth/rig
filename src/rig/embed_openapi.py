#!/usr/bin/env python3
"""Embed an OpenAPI JSON document in a C++20 header without changing its bytes."""

import sys


def generate(document):
    chunks = [document[start:start + 32] for start in range(0, len(document), 32)]
    if not chunks:
        chunks = [b""]
    lines = [
        "// Generated from RIG OpenAPI JSON; do not edit.",
        "#pragma once",
        "#include <string_view>",
        "namespace rig::generated {",
        "inline constexpr char openapi_bytes[] =",
    ]
    lines.extend('    "' + ''.join(f"\\{byte:03o}" for byte in chunk) + '"' for chunk in chunks)
    lines.extend([
        "    ;",
        f"inline constexpr std::string_view openapi_json{{openapi_bytes, {len(document)}}};",
        "} // namespace rig::generated",
        "",
    ])
    return "\n".join(lines)


if __name__ == "__main__":
    sys.stdout.write(generate(sys.stdin.buffer.read()))
