CXX ?= g++
RIG ?= rig
RIG_SOURCE ?=

.DELETE_ON_ERROR:

.PHONY: generate check clean

build/rig.json: inspect.cpp api.hpp $(RIG_SOURCE)
	mkdir -p build
	$(RIG) inspect inspect.cpp --cxx $(CXX) -- -I. > $@

build/openapi.json: build/rig.json $(RIG_SOURCE)
	$(RIG) openapi --title 'Catalog API' < $< > $@

generate: build/openapi.json
	cp build/openapi.json openapi.json

check: build/openapi.json
	$(RIG) validate < build/rig.json
	cmp build/openapi.json openapi.json

clean:
	rm -rf build
