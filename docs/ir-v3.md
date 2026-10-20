# RIG IR version 3

RIG's C++26 inspector writes one JSON object to standard output. The `rig`
generators read that object from standard input. `rig validate < rig.json`
checks the complete document and exits without output on success. The IR is a
build artifact; its version is independent of the Python package version.
`rig inspect inspect.cpp -- -I.` compiles and runs an inspection entry point,
validates its output, and writes the original IR bytes to standard output.
`rig inspect --header api.hpp --namespace app -- -I.` creates that entry point
from a C++20 API header. Repeat `--namespace` to include annotated operations
from several namespaces; reachable types and operations are emitted once in
the order of the requested namespaces.

```json
{
  "ir_version": 3,
  "types": [
    {"kind": "record", "name": "Item", "cpp_name": "app::Item", "fields": [
      {"name": "id", "type": {"kind": "builtin", "name": "int"}}
    ]},
    {"kind": "record", "name": "Error", "cpp_name": "app::Error", "fields": [
      {"name": "message", "type": {"kind": "builtin", "name": "string"}}
    ]}
  ],
  "operations": [
    {
      "name": "get_item",
      "cpp_name": "app::get_item",
      "method": "GET",
      "path": "/items/{id}",
      "parameters": [
        {"name": "id", "type": {"kind": "builtin", "name": "int"}}
      ],
      "returns": {"kind": "named", "name": "app::Item"},
      "errors": [
        {"status": 404, "type": {"kind": "named", "name": "app::Error"}}
      ]
    }
  ]
}
```

The top level has exactly `ir_version`, `types`, and `operations`. A type is a
`record` with ordered `fields` or an `enum` with ordered string `values`.
Records, fields, enums, enumerators, operations, and parameters have short
C++ identifier `name` values. Each type and operation also has a fully
qualified `cpp_name`, unique within its kind. Its final component must match
`name`. Named type references use that qualified name. OpenAPI schemas and
operation IDs keep short names when unique; colliding short names use dotted
qualified names such as `left.Result` and `right.Result`.

Every field, parameter, return value, and error body has a type reference:

| Kind | Members | Meaning |
| --- | --- | --- |
| `builtin` | `name`: `int`, `bool`, or `string` | C++ `int`, `bool`, or `std::string` |
| `named` | `name`: a declared qualified C++ type name | Record or enum |
| `array` | `items`: a type reference | `std::vector<T>` |
| `optional` | `value`: a type reference | `std::optional<T>` |

An operation has `name`, `cpp_name`, `method`, `path`, `parameters`, and `returns`.
`errors` is an optional ordered array of `{status, type}` objects; the
inspector writes it even when empty. Methods are uppercase `GET`, `POST`,
`PUT`, `PATCH`, or `DELETE`. Error status codes are unique integers from 400
through 599. Each method and path pair and each operation `cpp_name` is unique.

Paths start with `/` and contain literal segments or whole-segment `{name}`
placeholders. Literals use ASCII letters, digits, `.`, `_`, `~`, and `-`.
A placeholder must name exactly one parameter of type `int` or `string`.
Other parameters form the JSON request body; at most one is allowed. `GET`
and `DELETE` cannot have a body under the current convention. These rules
are shared by OpenAPI and the C++20 HTTP dispatch generator.

Record fields are all present in JSON. An `optional` field is present with
either a value or `null`; it does not mean the field can be omitted. Successful
operations have a JSON response with HTTP 200. Unknown keys and unsupported
types are rejected so that every generator interprets version 3 the same way.
Version 2 IR is rejected; regenerate it with `rig inspect` before running the
version 3 generators. `json-codec` and `http-routes` now use `cpp_name` and no
longer take `--namespace`.
