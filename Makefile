CXX ?= g++
PYTHON ?= python3

.PHONY: generate check clean

build/inspect: src/inspect.cpp dodger/api.hpp include/rig/route.hpp
	mkdir -p build
	$(CXX) -std=c++26 -freflection -DRIG_GENERATING -Iinclude -I. src/inspect.cpp -o $@

build/rig.json: build/inspect
	./build/inspect > $@

build/openapi.json: build/rig.json tools/openapi.py
	$(PYTHON) tools/openapi.py --title 'Dodger API' < build/rig.json > $@

generate: build/openapi.json
	cp build/openapi.json dodger/openapi.json

check: build/openapi.json
	$(CXX) -std=c++20 -Iinclude -I. -fsyntax-only src/cxx20_check.cpp
	$(PYTHON) -m unittest discover -s tools -p 'test_*.py'
	cmp build/openapi.json dodger/openapi.json

clean:
	rm -rf build
