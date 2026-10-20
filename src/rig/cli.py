"""Command line interface for RIG's build-time generators."""

import argparse
import json
import sys
from pathlib import Path

from .embed_openapi import generate as embed_openapi
from .http_routes import generate as http_routes
from .ir import validate
from .inspector import inspect
from .json_codec import generate as json_codec
from .openapi import convert


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    compiler_flags = ()
    if argv[:1] == ["inspect"] and "--" in argv:
        separator = argv.index("--")
        compiler_flags = argv[separator + 1:]
        argv = argv[:separator]
    parser = argparse.ArgumentParser(prog="rig")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("include-dir", help="print the installed C++ header directory")
    inspector = commands.add_parser("inspect", help="compile and run a C++26 inspector")
    inspector.add_argument("source", nargs="?", help="optional C++ inspection entry point")
    inspector.add_argument("--header", help="C++20 API header to inspect")
    inspector.add_argument("--namespace", action="append", help="namespace containing annotated operations; repeat for multiple namespaces")
    inspector.add_argument("--cxx", default="g++", help="C++26 compiler (default: g++)")
    inspector.epilog = (
        "Use either an entry point source or --header with one or more --namespace options. "
        "Pass additional compiler flags after --, for example: -- -Iinclude"
    )
    commands.add_parser("validate", help="validate IR on stdin")
    openapi = commands.add_parser("openapi", help="generate OpenAPI JSON from IR on stdin")
    openapi.add_argument("--title", default="API")
    openapi.add_argument("--version", default="0.1.0")
    openapi.add_argument("--omit-operation-ids", action="store_true",
                         help="omit inferred operation IDs from the generated document")
    codec = commands.add_parser("json-codec", help="generate C++20 JSON codecs")
    codec.add_argument("--api-header", required=True)
    routes = commands.add_parser("http-routes", help="generate C++20 HTTP dispatch")
    routes.add_argument("--codec-header", required=True)
    commands.add_parser("embed-openapi", help="embed OpenAPI bytes in a C++20 header")
    args = parser.parse_args(argv)
    try:
        if args.command == "include-dir":
            print(Path(__file__).resolve().parent / "include")
        elif args.command == "inspect":
            sys.stdout.buffer.write(inspect(
                args.source, args.cxx, compiler_flags,
                header=args.header, namespace=args.namespace,
            ))
        elif args.command == "embed-openapi":
            sys.stdout.write(embed_openapi(sys.stdin.buffer.read()))
        else:
            ir = json.load(sys.stdin)
            if args.command == "validate":
                validate(ir)
            elif args.command == "openapi":
                json.dump(convert(ir, args.title, args.version,
                                  include_operation_ids=not args.omit_operation_ids),
                          sys.stdout, indent=2)
                sys.stdout.write("\n")
            elif args.command == "json-codec":
                sys.stdout.write(json_codec(ir, args.api_header))
            else:
                sys.stdout.write(http_routes(ir, args.codec_header))
    except (KeyError, ValueError) as error:
        parser.exit(1, f"rig: {error}\n")


if __name__ == "__main__":
    main()
