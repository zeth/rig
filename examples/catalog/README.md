# Catalog example

This independent C++20 API shows how to use RIG outside Dodger. `api.hpp`
declares records, an enum, strings, an optional field, a list, and three HTTP
operations. `inspect.cpp` contains only registration calls; the reflection
logic comes from `include/rig/inspect.hpp`.

From the repository root, run `make generate` to update `openapi.json` or
`make check` to verify that it matches the declarations. This example is a
contract fixture; it does not include an HTTP server.
