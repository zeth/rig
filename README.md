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
RIG_ERROR(404, ErrorResponse)
Item get_item(ItemId id);

RIG_ROUTE(POST, "/items")
Item create_item(CreateItemRequest request);
```

The annotation macros are implemented in `include/rig/route.hpp` and disappear in
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

`include/rig/inspect.hpp` is the reusable C++26 reflection writer. Dodger's
`dodger/inspect.cpp` nominates its namespace once; RIG discovers its
`RIG_ROUTE` functions and the record and enum types reachable from their
signatures. `examples/catalog/inspect.cpp` still demonstrates explicit
registration. The writer extracts route annotations, parameters, return
types, typed error responses, record fields, and enum values into RIG IR JSON.
`tools/openapi.py` converts that IR to OpenAPI 3.1 JSON with Python's standard
library. `tools/json_codec.py` also generates a C++20 JSON codec header from
the same IR for Dodger's server. `tools/http_routes.py` generates its C++20
method and path dispatch, argument decoding, and operation calls. The catalog
example has no dependency on Dodger and exercises the same pipeline with a
different API. This split remains an experiment; the examples do not yet
establish whether the final OpenAPI generator belongs in Python or C++.

Current conventions are intentionally small: a parameter named in the route
is a path parameter; one remaining parameter becomes a JSON request body;
registered record fields are required; a successful operation returns
HTTP 200 with a JSON body; and `RIG_ERROR(status, Body)` declares an operation's
JSON error response. The IR currently describes `int`, `bool`,
`std::string`, registered records and enums, `std::vector<T>`, and
`std::optional<T>`. Enums become JSON strings matching their C++ enumerator
names. An optional field is always present and contains either a value or
`null`. Unsupported types and ambiguous inputs fail loudly.
Type names currently use their unqualified C++ identifier, so registering two
types with the same short name is rejected by the OpenAPI converter.
Server-level HTTP errors such as malformed headers and unexpected failures
are outside these per-operation declarations.
The current codec generator targets public aggregate records in one named
namespace, matching Dodger's API. The route generator currently supports
literal path segments and whole-segment `int` or string placeholders.

To add an app, include `rig/route.hpp` in its C++20 API header, annotate the
selected functions with `RIG_ROUTE`, and nominate the containing namespace in
a C++26 entry point:

```cpp
#include <examples/catalog/api.hpp>
#include <rig/inspect.hpp>
#include <iostream>

rig::writer output(std::cout);
output.add_namespace<^^catalog>();
output.finish();
```

Compile that registration file with `-std=c++26 -freflection -DRIG_GENERATING`
and the RIG include directory, then pipe its JSON output to
`python3 tools/openapi.py --title 'Catalog API'`. Namespace discovery sees
directly declared functions with a route annotation and follows their
referenced record and enum types. Unsupported references fail during OpenAPI
conversion. `rig::writer` also retains explicit `add_type` and
`add_operation` calls for cases where a namespace root is unsuitable.

Dodger now supplies a C++20 game engine and a localhost HTTP server for the
generated routes. The server uses `nlohmann_json` for JSON and POSIX sockets;
on Fedora, install `json-devel` if its header is unavailable. Run
`make server` to listen on `127.0.0.1:8765`. `make check` also exercises the
server over HTTP and checks its success and error responses against the generated
schemas.

Run `make play` in a terminal to launch the server, a Python bot that uses
the HTTP routes, and a terminal client for the human player. The bot and
client use only Python's standard library. See `dodger/README.md` for
controls and standalone commands.

Dodger's HTTP server uses generated C++20 code for its JSON format and route
dispatch. Socket handling, HTTP framing, and exception-to-status mapping
remain in the server. `make check` tests codec round trips, invalid actions,
and live responses against the generated OpenAPI schemas. It also changes a
route annotation in a temporary header and verifies that both OpenAPI and a
separately built live server follow the new path.
