# Qualified names example

This C++20 API has two records named `Result`, in `left` and `right`, and
operations named `read` in both namespaces. Header-mode inspection registers
all three namespaces, following their shared type references and emitting each
record once.
The `left` routes also check that a literal path wins over a matching string
placeholder even though the placeholder is declared first.
`service::lookup` maps thrown exceptions to its documented error responses,
including a derived exception listed before its base and a final
`std::exception` fallback for its documented 500.

Run `make check RIG=/path/to/rig` after installing RIG. The check validates
the IR, confirms distinct OpenAPI schemas and operation IDs, then
compiles and runs the generated C++20 JSON codecs and HTTP routes.
