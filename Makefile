CXX ?= g++
PYTHON ?= python3
CLIENT_PYTHON = build/client-venv/bin/python
CLIENT_BIN = $(abspath build/client-venv/bin)

.PHONY: generate check server play clean

build/inspect: dodger/inspect.cpp dodger/api.hpp include/rig/route.hpp include/rig/inspect.hpp
	mkdir -p build
	$(CXX) -std=c++26 -freflection -DRIG_GENERATING -Iinclude -I. dodger/inspect.cpp -o $@

build/rig.json: build/inspect
	./build/inspect > $@

build/openapi.json: build/rig.json tools/openapi.py
	$(PYTHON) tools/openapi.py --title 'Dodger API' < build/rig.json > $@

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

build/dodger_json.hpp: build/rig.json tools/json_codec.py
	$(PYTHON) tools/json_codec.py --namespace dodger --api-header dodger/api.hpp < build/rig.json > $@

build/dodger_routes.hpp: build/rig.json build/dodger_json.hpp tools/http_routes.py tools/openapi.py
	$(PYTHON) tools/http_routes.py --namespace dodger --codec-header build/dodger_json.hpp < build/rig.json > $@

build/catalog-inspect: examples/catalog/inspect.cpp examples/catalog/api.hpp include/rig/route.hpp include/rig/inspect.hpp
	mkdir -p build
	$(CXX) -std=c++26 -freflection -DRIG_GENERATING -Iinclude -I. examples/catalog/inspect.cpp -o $@

build/catalog-ir.json: build/catalog-inspect
	./build/catalog-inspect > $@

build/catalog-openapi.json: build/catalog-ir.json tools/openapi.py
	$(PYTHON) tools/openapi.py --title 'Catalog API' < build/catalog-ir.json > $@

build/dodger-server: dodger/game.cpp dodger/game.hpp dodger/server.cpp dodger/api.hpp build/dodger_routes.hpp
	$(CXX) -std=c++20 -Wall -Wextra -Wpedantic -Iinclude -I. dodger/game.cpp dodger/server.cpp -o $@

build/game-test: dodger/game.cpp dodger/game.hpp dodger/game_test.cpp dodger/api.hpp
	$(CXX) -std=c++20 -Wall -Wextra -Wpedantic -Iinclude -I. dodger/game.cpp dodger/game_test.cpp -o $@

build/json-codec-test: dodger/json_codec_test.cpp dodger/api.hpp build/dodger_json.hpp
	$(CXX) -std=c++20 -Wall -Wextra -Wpedantic -Iinclude -I. dodger/json_codec_test.cpp -o $@

generate: build/openapi.json build/catalog-openapi.json build/dodger_routes.hpp
	cp build/openapi.json dodger/openapi.json
	cp build/catalog-openapi.json examples/catalog/openapi.json

server: build/dodger-server
	./build/dodger-server

play: build/dodger-server build/dodger-client.ready
	$(CLIENT_PYTHON) dodger/play.py

check: build/openapi.json build/catalog-openapi.json build/dodger-server build/game-test build/json-codec-test build/dodger-client.ready
	$(CXX) -std=c++20 -Iinclude -I. -fsyntax-only src/cxx20_check.cpp
	$(CLIENT_PYTHON) -m unittest discover -s tools -p 'test_*.py'
	cmp build/openapi.json dodger/openapi.json
	cmp build/catalog-openapi.json examples/catalog/openapi.json
	./build/game-test
	./build/json-codec-test
	$(CLIENT_PYTHON) tools/test_server.py build/dodger-server dodger/openapi.json
	$(CLIENT_PYTHON) tools/test_route_change.py $(CXX)

clean:
	rm -rf build
