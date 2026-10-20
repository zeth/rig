# RIG IR version 2

RIG's C++26 inspector writes one JSON object to standard output. The `rig`
generators read that object from standard input. `rig validate < rig.json`
checks the complete document and exits without output on success. The IR is a
build artifact; its version is independent of the Python package version.
`rig inspect inspect.cpp -- -I.` compiles and runs an inspection entry point,
validates its output, and writes the original IR bytes to standard output.

```json
{
  "ir_version": 2,
  "types": [
    {"kind": "record", "name": "Item", "fields": [
      {"name": "id", "type": {"kind": "builtin", "name": "int"}}
    ]},
    {"kind": "record", "name": "Error", "fields": [
      {"name": "message", "type": {"kind": "builtin", "name": "string"}}
    ]}
  ],
  "operations": [
    {
      "name": "get_item",
      "method": "GET",
      "path": "/items/{id}",
      "parameters": [
        {"name": "id", "type": {"kind": "builtin", "name": "int"}}
      ],
      "returns": {"kind": "named", "name": "Item"},
      "errors": [
        {"status": 404, "type": {"kind": "named", "name": "Error"}}
      ]
    }
  ]
}
```

The top level has exactly `ir_version`, `types`, and `operations`. A type is a
`record` with ordered `fields` or an `enum` with ordered string `values`.
Records, fields, enums, enumerators, operations, and parameters use C++
identifiers. Each kind of name must be unique in its scope. Type names are
unique across the document and are currently unqualified C++ identifiers.

Every field, parameter, return value, and error body has a type reference:

| Kind | Members | Meaning |
| --- | --- | --- |
| `builtin` | `name`: `int`, `bool`, or `string` | C++ `int`, `bool`, or `std::string` |
| `named` | `name`: a declared type | Record or enum |
| `array` | `items`: a type reference | `std::vector<T>` |
| `optional` | `value`: a type reference | `std::optional<T>` |

An operation has `name`, `method`, `path`, `parameters`, and `returns`.
`errors` is an optional ordered array of `{status, type}` objects; the
inspector writes it even when empty. Methods are uppercase `GET`, `POST`,
`PUT`, `PATCH`, or `DELETE`. Error status codes are unique integers from 400
through 599. Each method and path pair and each operation name is unique.

Paths start with `/` and contain literal segments or whole-segment `{name}`
placeholders. Literals use ASCII letters, digits, `.`, `_`, `~`, and `-`.
A placeholder must name exactly one parameter of type `int` or `string`.
Other parameters form the JSON request body; at most one is allowed. `GET`
and `DELETE` cannot have a body under the current convention. These rules
are shared by OpenAPI and the C++20 HTTP dispatch generator.

Record fields are all present in JSON. An `optional` field is present with
either a value or `null`; it does not mean the field can be omitted. Successful
operations have a JSON response with HTTP 200. Unknown keys and unsupported
types are rejected so that every generator interprets version 2 the same way.
