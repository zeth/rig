CXX ?= g++
PYTHON ?= python3

.PHONY: generate check server clean

build/inspect: src/inspect.cpp dodger/api.hpp include/rig/route.hpp
	mkdir -p build
	$(CXX) -std=c++26 -freflection -DRIG_GENERATING -Iinclude -I. src/inspect.cpp -o $@

build/rig.json: build/inspect
	./build/inspect > $@

build/openapi.json: build/rig.json tools/openapi.py
	$(PYTHON) tools/openapi.py --title 'Dodger API' < build/rig.json > $@

build/dodger-server: dodger/game.cpp dodger/game.hpp dodger/server.cpp dodger/api.hpp
	$(CXX) -std=c++20 -Wall -Wextra -Wpedantic -Iinclude -I. dodger/game.cpp dodger/server.cpp -o $@

build/game-test: dodger/game.cpp dodger/game.hpp dodger/game_test.cpp dodger/api.hpp
	$(CXX) -std=c++20 -Wall -Wextra -Wpedantic -Iinclude -I. dodger/game.cpp dodger/game_test.cpp -o $@

generate: build/openapi.json
	cp build/openapi.json dodger/openapi.json

server: build/dodger-server
	./build/dodger-server

check: build/openapi.json build/dodger-server build/game-test
	$(CXX) -std=c++20 -Iinclude -I. -fsyntax-only src/cxx20_check.cpp
	$(PYTHON) -m unittest discover -s tools -p 'test_*.py'
	cmp build/openapi.json dodger/openapi.json
	./build/game-test
	$(PYTHON) tools/test_server.py build/dodger-server dodger/openapi.json

clean:
	rm -rf build
