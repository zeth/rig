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
       OpenAPI generator   C API generator
              │                │
              ▼                ▼
         openapi.yaml     C headers/wrappers
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
- **Extensible generation:** OpenAPI is the initial target, with C APIs and other interfaces supported through separate generators.
- **Deterministic output:** Generated interfaces are reproducible, testable and suitable for version control and CI validation.

### Intended developer experience

```cpp
RIG(GET, "/items/{id}")
Item get_item(ItemId id);

RIG(POST, "/items")
Item create_item(CreateItemRequest request);
```

These annotations are illustrative of RIG's proposed interface.

Developers continue writing ordinary C++20. RIG uses C++26 reflection at generation time to discover the annotated operations, extract their types and semantics, and produce an OpenAPI specification.

**The compiler understands the C++. RIG understands the interfaces. Existing tools consume the output.**

### Current prototype

The repository now contains a deliberately narrow working slice. From this directory,
run `make generate` to compile the C++26 inspector and regenerate
`dodger/openapi.json`; run `make check` to verify the C++20 header, conversion
rules, and generated-file drift. GCC 16 with `-freflection` and Python 3 are
required for generation. Ordinary consumers can compile `dodger/api.hpp` as
C++20 without reflection.

The inspector reads the explicitly registered declarations in
`src/inspect.cpp`, extracts route annotations, parameters, return types, and
record fields, then emits `build/rig.json`. `tools/openapi.py` converts that IR
to OpenAPI 3.1 JSON with Python's standard library. This split is an experiment:
the example is too small to determine whether the final OpenAPI generator
should stay in Python or move into C++.

Current conventions are intentionally small: a parameter named in the route
is a path parameter; one remaining parameter becomes a JSON request body;
registered record fields are required; and a successful operation returns
HTTP 200 with a JSON body. The IR currently describes `int`, `bool`,
`std::string`, registered records and enums, `std::vector<T>`, and
`std::optional<T>`. Enums become JSON strings matching their C++ enumerator
names. An optional field is always present and contains either a value or
`null`. Unsupported types and ambiguous inputs fail loudly.
Dodger now supplies a C++20 game engine and a localhost HTTP server for the
generated routes. The server uses `nlohmann_json` for JSON and POSIX sockets;
on Fedora, install `json-devel` if its header is unavailable. Run
`make server` to listen on `127.0.0.1:8765`. `make check` also exercises the
server over HTTP and checks its success responses against the generated
schemas.

The HTTP server's JSON encoding is still written by hand. This is a concrete
integration boundary to investigate before claiming RIG can keep a server's
wire representation in sync with its generated OpenAPI contract.
