"""Prove a changed C++ annotation changes OpenAPI and the live route."""

import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from test_server import request


def main():
    root = Path(__file__).resolve().parents[1]
    compiler, rig = sys.argv[1:]
    include_dir = subprocess.check_output([rig, "include-dir"], text=True).strip()
    source = (root / "api.hpp").read_text()
    original = 'RIG_ROUTE(GET, "/games/{id}")'
    changed = 'RIG_ROUTE(GET, "/matches/{id}")'
    assert source.count(original) == 1

    with tempfile.TemporaryDirectory(prefix="route-change-", dir=root / "build") as directory:
        temporary = Path(directory)
        (temporary / "build").mkdir()
        (temporary / "api.hpp").write_text(source.replace(original, changed))
        for name in ("game.hpp", "game.cpp", "server.cpp"):
            shutil.copyfile(root / name, temporary / name)
        shutil.copyfile(root / "build" / "dodger_json.hpp", temporary / "build" / "dodger_json.hpp")

        ir = json.loads(subprocess.check_output([
            rig, "inspect", "--header", "api.hpp", "--namespace", "dodger",
            "--cxx", compiler, "--", "-I.",
        ], cwd=temporary))
        openapi_json = subprocess.check_output(
            [rig, "openapi", "--title", "Dodger API"], input=json.dumps(ir), text=True
        )
        document = json.loads(openapi_json)
        paths = document["paths"]
        assert "/matches/{id}" in paths
        assert "/games/{id}" not in paths

        (temporary / "build" / "dodger_routes.hpp").write_text(subprocess.check_output(
            [rig, "http-routes", "--namespace", "dodger", "--codec-header", "build/dodger_json.hpp"],
            input=json.dumps(ir), text=True,
        ))
        (temporary / "build" / "dodger_openapi.hpp").write_text(subprocess.check_output(
            [rig, "embed-openapi"], input=openapi_json, text=True,
        ))
        server_path = temporary / "server"
        subprocess.run([
            compiler, "-std=c++20", f"-I{include_dir}", "-I.",
            "game.cpp", "server.cpp", "-o", str(server_path),
        ], cwd=temporary, check=True)

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
