# Qualified names example

This C++20 API has two records named `Result`, in `left` and `right`, and
operations named `read` in both namespaces. `inspect.cpp` registers the three
types and three operations explicitly. The `check` target also inspects the
`service` namespace directly from `api.hpp`, following its references to both
external records.

Run `make check RIG=/path/to/rig` after installing RIG. The check validates
both IR documents, confirms distinct OpenAPI schemas and operation IDs, then
compiles and runs the generated C++20 JSON codecs and HTTP routes.
