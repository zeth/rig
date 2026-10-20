"""Command line interface for RIG's build-time generators."""

import argparse
import json
import sys
from pathlib import Path

from .embed_openapi import generate as embed_openapi
from .http_routes import generate as http_routes
from .json_codec import generate as json_codec
from .openapi import convert


def main(argv=None):
    parser = argparse.ArgumentParser(prog="rig")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("include-dir", help="print the installed C++ header directory")
    openapi = commands.add_parser("openapi", help="generate OpenAPI JSON from IR on stdin")
    openapi.add_argument("--title", default="API")
    openapi.add_argument("--version", default="0.1.0")
    codec = commands.add_parser("json-codec", help="generate C++20 JSON codecs")
    codec.add_argument("--namespace", required=True)
    codec.add_argument("--api-header", required=True)
    routes = commands.add_parser("http-routes", help="generate C++20 HTTP dispatch")
    routes.add_argument("--namespace", required=True)
    routes.add_argument("--codec-header", required=True)
    commands.add_parser("embed-openapi", help="embed OpenAPI bytes in a C++20 header")
    args = parser.parse_args(argv)
    try:
        if args.command == "include-dir":
            print(Path(__file__).resolve().parent / "include")
        elif args.command == "embed-openapi":
            sys.stdout.write(embed_openapi(sys.stdin.buffer.read()))
        else:
            ir = json.load(sys.stdin)
            if args.command == "openapi":
                json.dump(convert(ir, args.title, args.version), sys.stdout, indent=2)
                sys.stdout.write("\n")
            elif args.command == "json-codec":
                sys.stdout.write(json_codec(ir, args.namespace, args.api_header))
            else:
                sys.stdout.write(http_routes(ir, args.namespace, args.codec_header))
    except (KeyError, ValueError) as error:
        parser.exit(1, f"rig: {error}\n")


if __name__ == "__main__":
    main()
