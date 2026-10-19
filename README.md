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
RIG_ROUTE(GET, "/items/{id}")
Item get_item(ItemId id);

RIG_ROUTE(POST, "/items")
Item create_item(CreateItemRequest request);
```

The route macro is implemented in `include/rig/route.hpp` and disappears in
ordinary C++20 builds.

Developers continue writing ordinary C++20. RIG uses C++26 reflection at generation time to discover the annotated operations, extract their types and semantics, and produce an OpenAPI specification.

**The compiler understands the C++. RIG understands the interfaces. Existing tools consume the output.**

### Current prototype

The repository now contains a deliberately narrow working slice. From this
directory, run `make generate` to regenerate Dodger and the independent
catalog example; run `make check` to verify both C++20 headers, conversion
rules, and generated-file drift. GCC 16 with `-freflection` and Python 3 are
required for generation. Ordinary consumers compile their API headers as
C++20 without reflection.

`include/rig/inspect.hpp` is the reusable C++26 reflection writer. Each app
provides a small registration file: `dodger/inspect.cpp` or
`examples/catalog/inspect.cpp`. The writer extracts route annotations,
parameters, return types, record fields, and enum values into RIG IR JSON.
`tools/openapi.py` converts that IR to OpenAPI 3.1 JSON with Python's standard
library. The catalog example has no dependency on Dodger and exercises the
same pipeline with a different API. This split remains an experiment; the
examples do not yet establish whether the final OpenAPI generator belongs in
Python or C++.

Current conventions are intentionally small: a parameter named in the route
is a path parameter; one remaining parameter becomes a JSON request body;
registered record fields are required; and a successful operation returns
HTTP 200 with a JSON body. The IR currently describes `int`, `bool`,
`std::string`, registered records and enums, `std::vector<T>`, and
`std::optional<T>`. Enums become JSON strings matching their C++ enumerator
names. An optional field is always present and contains either a value or
`null`. Unsupported types and ambiguous inputs fail loudly.
Type names currently use their unqualified C++ identifier, so registering two
types with the same short name is rejected by the OpenAPI converter.

To add an app, include `rig/route.hpp` in its C++20 API header, annotate the
selected functions with `RIG_ROUTE`, and create a C++26 registration file using
`rig::writer`:

```cpp
#include <examples/catalog/api.hpp>
#include <rig/inspect.hpp>
#include <iostream>

rig::writer output(std::cout);
output.add_type<^^catalog::Availability>();
output.add_type<^^catalog::Item>();
output.add_operation<^^catalog::get_item>();
output.finish();
```

Compile that registration file with `-std=c++26 -freflection -DRIG_GENERATING`
and the RIG include directory, then pipe its JSON output to
`python3 tools/openapi.py --title 'Catalog API'`. Register every referenced
record and enum before the operations; unsupported references fail during
OpenAPI conversion.

Dodger now supplies a C++20 game engine and a localhost HTTP server for the
generated routes. The server uses `nlohmann_json` for JSON and POSIX sockets;
on Fedora, install `json-devel` if its header is unavailable. Run
`make server` to listen on `127.0.0.1:8765`. `make check` also exercises the
server over HTTP and checks its success responses against the generated
schemas.

Run `make play` in a terminal to launch the server, a Python bot that uses
the HTTP routes, and a terminal client for the human player. The bot and
client use only Python's standard library. See `dodger/README.md` for
controls and standalone commands.

The HTTP server's JSON encoding is still written by hand. This is a concrete
integration boundary to investigate before claiming RIG can keep a server's
wire representation in sync with its generated OpenAPI contract.
