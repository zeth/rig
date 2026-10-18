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
