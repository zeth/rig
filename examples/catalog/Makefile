CXX ?= g++
RIG ?= rig
RIG_SOURCE ?=
RIG_INCLUDE = $(shell $(RIG) include-dir)

.PHONY: generate check clean

build/inspect: inspect.cpp api.hpp
	mkdir -p build
	$(CXX) -std=c++26 -freflection -DRIG_GENERATING -I$(RIG_INCLUDE) -I. inspect.cpp -o $@

build/rig.json: build/inspect
	./build/inspect > $@

build/openapi.json: build/rig.json $(RIG_SOURCE)
	$(RIG) openapi --title 'Catalog API' < $< > $@

generate: build/openapi.json
	cp build/openapi.json openapi.json

check: build/openapi.json
	cmp build/openapi.json openapi.json

clean:
	rm -rf build
