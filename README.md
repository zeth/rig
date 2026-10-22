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
#include <rig/result.hpp>

RIG_ROUTE(GET, "/items/{id}")
rig::result<Item, rig::error<404, ErrorResponse>> get_item(ItemId id);

RIG_ROUTE(GET, "/items")
ItemList list_items(std::optional<int> limit RIG_QUERY);

RIG_ROUTE(POST, "/items")
Item create_item(CreateItemRequest request);
```

The route annotation macro is implemented in `src/rig/include/rig/route.hpp`
and disappears in ordinary C++20 builds. `rig/result.hpp` supplies a small
C++20 return type for operations with declared errors.

Developers continue writing ordinary C++20. RIG uses C++26 reflection at generation time to discover the annotated operations, extract their types and semantics, and produce an OpenAPI specification.

**The compiler understands the C++. RIG understands the interfaces. Existing tools consume the output.**

### Project layout

RIG is an installable Python command line tool with its C++ headers bundled
in the package. `src/rig/include/rig/route.hpp` supplies C++20 annotations;
`inspect.hpp` is the C++26 reflection writer. `src/rig/*.py` validates and
transforms the reflected IR. `tests/` contains RIG tests. Each directory in
`examples/` has its own build and checks and uses only the installed `rig`
command and headers. Dodger is a complete example app; Catalog is a small
contract example. `docs/performance.md` records the runtime cost of generated
code and how to reduce it if it ever matters.

Install locally with `python3 -m pip install .`, then run `rig --help` and
`rig include-dir` to find the installed C++ headers. To check this checkout,
run `make check`; it creates an editable local installation under `build/venv`,
runs RIG's tests, and invokes each example's own `check` target. GCC 16 with
`-freflection` and Python 3.11 or later are required. Dodger's check installs
its pinned client tools in its own ignored virtual environment.

The reflection writer extracts route annotations, parameters, return types,
typed error responses, record fields, and enum values into versioned RIG IR
JSON. `rig openapi` emits OpenAPI 3.2 JSON, or YAML with `--format yaml`; `rig json-codec` emits C++20
`nlohmann::json` codecs; `rig http-routes` emits C++20 dispatch; and
`rig embed-openapi` emits a header containing the exact OpenAPI bytes. Each
generator reads IR (or OpenAPI bytes for `embed-openapi`) on standard input
and writes its result on standard output.
`rig inspect` creates a C++26 entry point from a C++20 header and one or more namespaces,
or compiles an explicit entry point. It runs the inspector, validates its IR,
and writes that IR to standard output. Pass application include paths and
other compiler flags after `--`; use `--cxx` to select a compiler.
For an operation with `RIG_CONTEXT` parameters, generated HTTP dispatch accepts
a host context object whose members match those parameter names. The context
is excluded from OpenAPI and passed to the C++ operation in declaration order.
Run `rig validate < rig.json` to check the shared IR contract without generating
output. See [IR version 12](docs/ir-v12.md) for its format and current rules.
Use `RIG_RANGE(minimum, maximum)` on an integer parameter to publish inclusive
bounds in OpenAPI and enforce them in generated HTTP dispatch.

Current conventions are intentionally small: a parameter named in the route
is a path parameter; `RIG_QUERY` after a scalar parameter name marks a query
parameter, required unless its type is `std::optional<T>`; one remaining
unmarked parameter becomes a JSON request body;
registered record fields are required; a successful operation returns
HTTP 200 with a JSON body; and `rig::result<Success, rig::error<Status, Body>...>`
declares operation errors. The generated HTTP dispatcher returns the chosen
status and JSON body. The IR currently describes `int`, `long long`,
`double`, `bool`, `std::string`, `nlohmann::json` objects, registered records
and enums, `std::vector<T>`, `std::optional<T>`, and
`std::map<std::string, T>`. Enums become JSON strings matching their C++ enumerator
names. An optional field is always present and contains either a value or
`null`. Unsupported types and ambiguous inputs fail loudly.
The IR carries qualified C++ names for types and operations. OpenAPI uses short
schema names and operation IDs when unique, and dotted qualified names when
short names collide. `examples/qualified` checks this across namespaces.
Server-level HTTP errors can be documented with `RIG_ERROR_RESPONSE` even when
the function returns a plain success value. The generated dispatcher then calls
the function directly; the hosting server remains responsible for those errors.
An error response can also name the exception types that produce it:

```cpp
RIG_ROUTE(GET, "/projects/{id}")
RIG_ERROR_RESPONSE(404, ErrorResponse, "Not found", ProjectNotFound)
RIG_ERROR_RESPONSE(500, ErrorResponse, "Internal error", std::exception)
Project get_project(std::string id);

ErrorResponse rig_error_body(std::type_identity<ErrorResponse>, int status,
                             const std::exception& error);
```

Generated dispatch then catches each named type, in annotation order, and
returns that status with the body built by `rig_error_body`. The application
declares `rig_error_body` beside the body type so argument-dependent lookup
finds it, and can overload it for particular exception types. A type listed
after one of its bases would never be caught, so the inspector rejects it.
Unmapped exceptions still propagate to the hosting server.
The current codec generator targets public aggregate records. The route generator currently supports
literal path segments and whole-segment `int` or string placeholders.
IR validation rejects ambiguous overlapping routes, and generated dispatch
places more specific paths first.
Generated dispatch also returns a documented 400 response when an integer path
value, percent-encoded string path value, or JSON body cannot be decoded. It
matches the path without its query string and decodes string path parameters
after matching, including encoded slashes within a parameter. It calls the
application operation only after decoding succeeds.
By default that 400 body is `{"code": "invalid_request", "message": ...}`.
`RIG_VALIDATION_ERROR(ErrorResponse, "Bad request")` on the service record
makes dispatch build it with the same `rig_error_body` function used for mapped
exceptions, and OpenAPI documents that body instead.
`RIG_UNAUTHORIZED(ErrorResponse, "Unauthorized")` beside `RIG_BEARER_AUTH`
documents the host's 401 on every operation, and `RIG_PUBLIC` marks an
operation that needs no token: it gets `security: []` and no 401. The host
asks `rig_http::is_public(method, path)` before authenticating.
When dispatch returns no response, `rig_http::is_host_served(method, path)`
says whether the request names a `RIG_HOST_RESPONSE` operation for the host to
serve; otherwise it names no operation, so the host can answer 404 and never
serve a route the contract leaves out.
`RIG_INTERNAL_ERROR(ErrorResponse, "Internal server error")` makes every
operation turn an otherwise unmapped `std::exception` into a documented 500.
`RIG_METHOD_NOT_ALLOWED(ErrorResponse, "Method not allowed")` makes dispatch
answer a declared path with an undeclared method with 405, setting
`response.allow` for the `Allow` header, instead of leaving it to the host.

A `nlohmann::json` field is a free-form JSON object, a
`std::map<std::string, T>` field is an object of `T` values, and
`RIG_SUCCESS_STATUS(201)` gives an operation a success status other than 200.
An operation that answers with one of several statuses returns
`rig::success<Body>{status, body}` and declares each status besides its
`RIG_SUCCESS_STATUS` with `RIG_SUCCESS_RESPONSE(201, "Created")`; dispatch
answers any other status with the service's internal error.
`RIG_WRITE_ONLY` marks a field clients send but responses never contain, such
as a secret. `RIG_FORMAT("uuid")`, `RIG_MIN_LENGTH(1)`, `RIG_MAX_LENGTH(40)`
and `RIG_DEFAULT(50)` describe fields and parameters, and
`RIG_STRING_VALUES(...)` restricts a parameter to listed strings. A
`std::optional<T>` body parameter makes the request body optional.
`RIG_PATTERN("^[0-9a-f]+$")` restricts a string. `RIG_VALUE_TYPE` on a
one-field struct gives a named schema that is not an object, such as a
constrained string, and a record that extends another becomes `allOf`.
A `std::variant<A, B>` is `oneOf`: decoding accepts a value
only when exactly one alternative does. `RIG_MIN_PROPERTIES(1)` makes a
partial update change something, and
`RIG_OPERATION_ID("name")` fixes an operation's `operationId`. An event
stream declares `RIG_SSE_EVENT("ready", Ready)` for each event and reads
`Last-Event-ID` through a parameter marked `RIG_HEADER("Last-Event-ID")`.
Any operation can read a request header that way; the host passes
`rig_http::dispatch` a lookup function as its last argument.

`RIG_HOST_RESPONSE("text/event-stream")` declares an operation whose response
the host writes, such as an event stream or a file download. RIG documents it
from the declaration, which need not be defined, and generated dispatch hands
its requests back to the host.

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
