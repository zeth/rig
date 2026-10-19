"""Exercise the live Dodger routes against RIG's generated response schemas."""

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def validate(value, schema, components):
    if "$ref" in schema:
        validate(value, components[schema["$ref"].split("/")[-1]], components)
    elif "anyOf" in schema:
        failures = []
        for choice in schema["anyOf"]:
            try:
                validate(value, choice, components)
                return
            except AssertionError as error:
                failures.append(str(error))
        raise AssertionError(f"no schema matched {value!r}: {failures}")
    elif schema["type"] == "object":
        assert isinstance(value, dict)
        assert set(schema["required"]) <= set(value)
        if schema.get("additionalProperties") is False:
            assert set(value) <= set(schema["properties"])
        for key, field in schema["properties"].items():
            if key in value:
                validate(value[key], field, components)
    elif schema["type"] == "array":
        assert isinstance(value, list)
        for item in value:
            validate(item, schema["items"], components)
    elif schema["type"] == "integer":
        assert type(value) is int
    elif schema["type"] == "boolean":
        assert type(value) is bool
    elif schema["type"] == "string":
        assert isinstance(value, str)
        if "enum" in schema:
            assert value in schema["enum"]
    elif schema["type"] == "null":
        assert value is None
    else:
        raise AssertionError(f"unsupported test schema: {schema}")


def request(url, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def main():
    server_path, spec_path = sys.argv[1:]
    spec = json.loads(Path(spec_path).read_text())
    components = spec["components"]["schemas"]
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = subprocess.Popen(
        [server_path, str(port)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                status, state = request(base + "/games/1")
                break
            except urllib.error.URLError:
                if server.poll() is not None:
                    raise AssertionError(f"server exited: {server.stderr.read()}")
                time.sleep(0.02)
        else:
            raise AssertionError("server did not start")
        assert status == 200
        get_schema = spec["paths"]["/games/{id}"]["get"]["responses"]["200"]
        get_schema = get_schema["content"]["application/json"]["schema"]
        validate(state, get_schema, components)
        assert state["status"] == "Waiting"
        assert state["winner"] is None

        human_path = "/games/1/players/1/actions"
        bot_path = "/games/1/players/2/actions"
        action = {"move": "Stay", "shove": False}
        for path in (human_path, bot_path):
            status, state = request(base + path, "POST", action)
            assert status == 200
            schema_path = path.replace("/games/1/", "/games/{id}/")
            operation = spec["paths"][schema_path]["post"]
            validate(action, operation["requestBody"]["content"]["application/json"]["schema"], components)
            validate(state, operation["responses"]["200"]["content"]["application/json"]["schema"], components)
        assert state["status"] == "Running"
        time.sleep(0.2)
        status, state = request(base + "/games/1")
        assert status == 200 and state["tick"] > 0
        validate(state, get_schema, components)
        assert request(base + "/games/2")[0] == 404
        assert request(base + bot_path, "POST", {"move": "Jump", "shove": False})[0] == 400
        print("live Dodger HTTP contract: OK")
    finally:
        server.terminate()
        try:
            server.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            server.kill()
            server.communicate()


if __name__ == "__main__":
    main()
