CXX ?= g++
PYTHON ?= python3
RIG = $(abspath build/venv/bin/rig)

.PHONY: check examples clean

build/venv/bin/rig: pyproject.toml $(wildcard src/rig/*.py src/rig/include/rig/*.hpp)
	$(PYTHON) -m venv --clear --system-site-packages build/venv
	build/venv/bin/python -m pip install --no-build-isolation --no-deps -e .

check: build/venv/bin/rig
	build/venv/bin/python -m unittest discover -s tests
	$(CXX) -std=c++20 -I$$($(RIG) include-dir) -fsyntax-only tests/cxx20_check.cpp
	$(MAKE) examples

examples: build/venv/bin/rig
	@for example in examples/*; do \
		if test -f "$$example/Makefile"; then \
			$(MAKE) -C "$$example" check RIG=$(RIG) RIG_SOURCE=$(RIG) || exit $$?; \
		fi; \
	done

clean:
	rm -rf build
