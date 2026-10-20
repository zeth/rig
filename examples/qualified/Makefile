CXX ?= g++
PYTHON ?= python3
RIG ?= rig
RIG_SOURCE ?=
RIG_INCLUDE = $(shell $(RIG) include-dir)

.DELETE_ON_ERROR:
.PHONY: check clean

build/rig.json: inspect.cpp api.hpp $(RIG_SOURCE)
	mkdir -p build
	$(RIG) inspect inspect.cpp --cxx $(CXX) -- -I. > $@

build/auto.json: api.hpp $(RIG_SOURCE)
	mkdir -p build
	$(RIG) inspect --header api.hpp --namespace service --cxx $(CXX) -- -I. > $@

build/openapi.json: build/rig.json $(RIG_SOURCE)
	$(RIG) openapi < $< > $@

build/codec.hpp: build/rig.json $(RIG_SOURCE)
	$(RIG) json-codec --api-header api.hpp < $< > $@

build/routes.hpp: build/rig.json build/codec.hpp $(RIG_SOURCE)
	$(RIG) http-routes --codec-header build/codec.hpp < $< > $@

build/check: check.cpp api.hpp build/routes.hpp
	$(CXX) -std=c++20 -Wall -Wextra -Wpedantic -I$(RIG_INCLUDE) -I. check.cpp -o $@

check: build/openapi.json build/auto.json build/check
	$(RIG) validate < build/rig.json
	$(RIG) validate < build/auto.json
	$(PYTHON) check_openapi.py
	./build/check

clean:
	rm -rf build
