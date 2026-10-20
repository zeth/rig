CXX ?= g++
PYTHON ?= python3
RIG ?= rig
RIG_SOURCE ?=
RIG_INCLUDE = $(shell $(RIG) include-dir)
CLIENT_PYTHON = build/client-venv/bin/python
CLIENT_BIN = $(abspath build/client-venv/bin)

.DELETE_ON_ERROR:

.PHONY: generate check server play clean

build/rig.json: api.hpp $(RIG_SOURCE)
	mkdir -p build
	$(RIG) inspect --header api.hpp --namespace dodger --cxx $(CXX) -- -I. > $@

build/openapi.json: build/rig.json $(RIG_SOURCE)
	$(RIG) openapi --title 'Dodger API' < $< > $@

build/dodger_openapi.hpp: build/openapi.json $(RIG_SOURCE)
	$(RIG) embed-openapi < $< > $@

build/dodger_json.hpp: build/rig.json $(RIG_SOURCE)
	$(RIG) json-codec --namespace dodger --api-header api.hpp < $< > $@

build/dodger_routes.hpp: build/rig.json build/dodger_json.hpp $(RIG_SOURCE)
	$(RIG) http-routes --namespace dodger --codec-header build/dodger_json.hpp < $< > $@

build/client-venv/.ready: requirements-client.txt
	$(PYTHON) -m venv build/client-venv
	$(CLIENT_PYTHON) -m pip install -r requirements-client.txt
	touch $@

build/openapi.validated: build/openapi.json build/client-venv/.ready
	build/client-venv/bin/openapi-spec-validator build/openapi.json
	touch $@

build/dodger-client.ready: build/openapi.validated
	PATH=$(CLIENT_BIN):$$PATH build/client-venv/bin/openapi-python-client generate --path build/openapi.json --meta none --fail-on-warning --overwrite --output-path build/dodger_api_client
	touch $@

build/dodger-server: game.cpp game.hpp server.cpp api.hpp build/dodger_routes.hpp build/dodger_openapi.hpp
	$(CXX) -std=c++20 -Wall -Wextra -Wpedantic -I$(RIG_INCLUDE) -I. game.cpp server.cpp -o $@

build/game-test: game.cpp game.hpp tests/game_test.cpp api.hpp
	$(CXX) -std=c++20 -Wall -Wextra -Wpedantic -I$(RIG_INCLUDE) -I. game.cpp tests/game_test.cpp -o $@

build/json-codec-test: tests/json_codec_test.cpp api.hpp build/dodger_json.hpp
	$(CXX) -std=c++20 -Wall -Wextra -Wpedantic -I$(RIG_INCLUDE) -I. tests/json_codec_test.cpp -o $@

generate: build/openapi.json build/dodger_routes.hpp build/dodger_openapi.hpp
	cp build/openapi.json openapi.json

server: build/dodger-server
	./build/dodger-server

play: build/dodger-server build/dodger-client.ready
	$(CLIENT_PYTHON) play.py

check: build/openapi.json build/dodger-server build/game-test build/json-codec-test build/dodger-client.ready
	$(RIG) validate < build/rig.json
	$(CLIENT_PYTHON) -m unittest discover -s tests -p 'test_*.py'
	cmp build/openapi.json openapi.json
	./build/game-test
	./build/json-codec-test
	$(CLIENT_PYTHON) tests/test_server.py build/dodger-server openapi.json
	$(CLIENT_PYTHON) tests/test_route_change.py $(CXX) $(RIG)

clean:
	rm -rf build
