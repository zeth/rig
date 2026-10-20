## RIG — Reflection Interface Generator

**Generate portable interfaces from existing C++ declarations using C++26 static reflection.**

RIG uses modern compiler reflection to inspect ordinary C++20 code, extract its public API structure and generate interface definitions without requiring changes to the application's compiler or runtime dependencies.

### Architecture

```text
              C++20 source code
              + light annotations
                      │
                      ▼
           ┌─────────────────────┐
           │  GCC 16 / C++26     │
           │                     │
           │  Parse C++ source   │
           │  Build compiler AST │
           │  Resolve types and  │
           │  declarations       │
           └──────────┬──────────┘
                      │
                      ▼
              C++26 reflection
                  ^^Type
                      │
                      ▼
               std::meta::info
                      │
                      ▼
           ┌─────────────────────┐
           │ Reflection inspector│
           │                     │
           │ Enumerate types     │
           │ Enumerate functions │
           │ Inspect parameters  │
           │ Inspect annotations │
           │ Generate extraction │
           │ code                │
           └──────────┬──────────┘
                      │
                      ▼
             Compiled inspector
                      │
            ──────────┼──────────
             Compile  │  Runtime
            ──────────┼──────────
                      │
                      ▼
              Extracted metadata
                      │
                      ▼
           ┌─────────────────────┐
           │       RIG IR        │
           │                     │
           │ Types and fields    │
           │ Operations          │
           │ Parameters          │
           │ Annotations         │
           │ Interface semantics │
           └──────────┬──────────┘
                      │
              ┌───────┴────────┐
              │                │
              ▼                ▼
       OpenAPI generator   future generators
              │                │
              ▼                ▼
         openapi.json
              │
              ▼
       Existing tools such as
       openapi-python-client
```

### Design principles

- **Unopinionated input:** RIG inspects existing C++20 declarations without imposing an application framework, object model or runtime library.
- **Minimal annotations:** Developers provide only metadata that reflection cannot infer, such as HTTP methods and routes.
- **Modern tooling, portable output:** GCC 16 and C++26 are required for reflection, not for compiling the original application or consuming generated interfaces.
- **Neutral intermediate representation:** Reflection extracts information into a common IR, independent of any output format.
- **Extensible generation:** OpenAPI is the initial target; other interfaces could use separate generators.
- **Deterministic output:** Generated interfaces are reproducible, testable and suitable for version control and CI validation.

### Intended developer experience

```cpp
RIG_ROUTE(GET, "/items/{id}")
RIG_ERROR(404, ErrorResponse)
Item get_item(ItemId id);

RIG_ROUTE(POST, "/items")
Item create_item(CreateItemRequest request);
```

The annotation macros are implemented in `src/rig/include/rig/route.hpp` and disappear in
ordinary C++20 builds.

Developers continue writing ordinary C++20. RIG uses C++26 reflection at generation time to discover the annotated operations, extract their types and semantics, and produce an OpenAPI specification.

**The compiler understands the C++. RIG understands the interfaces. Existing tools consume the output.**

### Project layout

RIG is an installable Python command line tool with its C++ headers bundled
in the package. `src/rig/include/rig/route.hpp` supplies C++20 annotations;
`inspect.hpp` is the C++26 reflection writer. `src/rig/*.py` validates and
transforms the reflected IR. `tests/` contains RIG tests. Each directory in
`examples/` has its own build and checks and uses only the installed `rig`
command and headers. Dodger is a complete example app; Catalog is a small
contract example.

Install locally with `python3 -m pip install .`, then run `rig --help` and
`rig include-dir` to find the installed C++ headers. To check this checkout,
run `make check`; it creates an editable local installation under `build/venv`,
runs RIG's tests, and invokes each example's own `check` target. GCC 16 with
`-freflection` and Python 3.11 or later are required. Dodger's check installs
its pinned client tools in its own ignored virtual environment.

The reflection writer extracts route annotations, parameters, return types,
typed error responses, record fields, and enum values into versioned RIG IR
JSON. `rig openapi` emits OpenAPI 3.1 JSON; `rig json-codec` emits C++20
`nlohmann::json` codecs; `rig http-routes` emits C++20 dispatch; and
`rig embed-openapi` emits a header containing the exact OpenAPI bytes. Each
generator reads IR (or OpenAPI bytes for `embed-openapi`) on standard input
and writes its result on standard output.
`rig inspect` creates a C++26 entry point from a C++20 header and one or more namespaces,
or compiles an explicit entry point. It runs the inspector, validates its IR,
and writes that IR to standard output. Pass application include paths and
other compiler flags after `--`; use `--cxx` to select a compiler.
Run `rig validate < rig.json` to check the shared IR contract without generating
output. See [IR version 3](docs/ir-v3.md) for its format and current rules.

Current conventions are intentionally small: a parameter named in the route
is a path parameter; one remaining parameter becomes a JSON request body;
registered record fields are required; a successful operation returns
HTTP 200 with a JSON body; and `RIG_ERROR(status, Body)` declares an operation's
JSON error response. The IR currently describes `int`, `bool`,
`std::string`, registered records and enums, `std::vector<T>`, and
`std::optional<T>`. Enums become JSON strings matching their C++ enumerator
names. An optional field is always present and contains either a value or
`null`. Unsupported types and ambiguous inputs fail loudly.
The IR carries qualified C++ names for types and operations. OpenAPI uses short
schema names and operation IDs when unique, and dotted qualified names when
short names collide. `examples/qualified` checks this across namespaces.
Server-level HTTP errors such as malformed headers and unexpected failures
are outside these per-operation declarations.
The current codec generator targets public aggregate records. The route generator currently supports
literal path segments and whole-segment `int` or string placeholders.

To add an app, include `rig/route.hpp` in its C++20 API header, annotate the
selected functions with `RIG_ROUTE`, and name its namespace at generation
time:

```sh
rig inspect --header api.hpp --namespace catalog -- -I. > rig.json
rig openapi --title 'Catalog API' < rig.json > openapi.json
```

Repeat `--namespace` when annotated operations span several namespaces. RIG
collects their reachable record and enum types once, even when routes in
different namespaces share a type.

RIG creates the C++26 entry point, supplies the reflection flags and its
installed include directory, and validates the resulting IR. Namespace discovery sees
directly declared functions with a route annotation and follows their
referenced record and enum types. Unsupported references fail during IR
validation. For explicit registration, write a C++26 entry point using
`rig::writer` and pass it to `rig inspect inspect.cpp -- -I.`. Catalog exercises
that form; Dodger uses header and namespace mode.

In `examples/dodger`, run `make server` or `make play` after installing RIG.
Its C++20 server uses the generated codec and dispatch, and serves the generated
document from embedded bytes. Dodger's own `make check` validates the document,
generates a Python client, checks live HTTP responses, and proves that changing
an annotation changes both the document and a rebuilt server. See
`examples/dodger/README.md` for controls and commands.
