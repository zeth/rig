"""Prove a changed C++ annotation changes OpenAPI and the live route."""

import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from embed_openapi import generate as embed_openapi
from http_routes import generate
from openapi import convert
from test_server import request


def main():
    root = Path(__file__).resolve().parents[1]
    source = (root / "dodger" / "api.hpp").read_text()
    original = 'RIG_ROUTE(GET, "/games/{id}")'
    changed = 'RIG_ROUTE(GET, "/matches/{id}")'
    assert source.count(original) == 1

    with tempfile.TemporaryDirectory(prefix="route-change-", dir=root / "build") as directory:
        temporary = Path(directory)
        (temporary / "dodger").mkdir()
        (temporary / "build").mkdir()
        (temporary / "dodger" / "api.hpp").write_text(source.replace(original, changed))

        inspector = temporary / "inspect"
        subprocess.run([
            sys.argv[1], "-std=c++26", "-freflection", "-DRIG_GENERATING",
            f"-I{temporary}", "-Iinclude", "-I.", "dodger/inspect.cpp", "-o", str(inspector),
        ], cwd=root, check=True)
        ir = json.loads(subprocess.check_output([inspector], cwd=root))
        document = convert(ir, title="Dodger API")
        paths = document["paths"]
        assert "/matches/{id}" in paths
        assert "/games/{id}" not in paths

        (temporary / "build" / "dodger_routes.hpp").write_text(
            generate(ir, "dodger", "build/dodger_json.hpp")
        )
        openapi_json = json.dumps(document, indent=2) + "\n"
        (temporary / "build" / "dodger_openapi.hpp").write_text(
            embed_openapi(openapi_json.encode())
        )
        server_path = temporary / "server"
        subprocess.run([
            sys.argv[1], "-std=c++20", f"-I{temporary}", "-Iinclude", "-I.",
            "dodger/game.cpp", "dodger/server.cpp", "-o", str(server_path),
        ], cwd=root, check=True)

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        server = subprocess.Popen(
            [server_path, str(port)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        base = f"http://127.0.0.1:{port}"
        try:
            for _ in range(100):
                try:
                    status, state = request(base + "/matches/1")
                    break
                except OSError:
                    if server.poll() is not None:
                        raise AssertionError(f"server exited: {server.stderr.read()}")
                    time.sleep(0.02)
            else:
                raise AssertionError("server did not start")
            assert status == 200 and state["id"] == 1
            assert request(base + "/games/1")[0] == 404
            with urllib.request.urlopen(base + "/openapi.json", timeout=2) as response:
                assert response.status == 200
                assert response.read() == openapi_json.encode()
        finally:
            server.terminate()
            try:
                server.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                server.kill()
                server.communicate()
    print("route annotation change updates OpenAPI and live server: OK")


if __name__ == "__main__":
    main()
