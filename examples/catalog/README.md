# Catalog example

This independent C++20 API shows how to use RIG outside Dodger. `api.hpp`
declares records, an enum, strings, an optional field, a list, and three HTTP
operations. `inspect.cpp` contains only registration calls; the reflection
logic comes from RIG's installed `inspect.hpp`.
`list_items` uses a required `limit` query parameter declared with `RIG_QUERY`.
The Makefile calls `rig inspect` to compile and run that entry point.

Install RIG, then from this directory run `make generate` to update
`openapi.json` or `make check` to verify that it matches the declarations. This is a
contract fixture; it does not include an HTTP server.
