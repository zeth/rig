# RIG IR version 6

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
  "ir_version": 6,
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
inspector writes it even when empty. A function returning `rig::result<Success,
rig::error<Status, Body>...>` supplies both the success type and its declared
error responses. The generated HTTP dispatcher returns the selected status
and encoded body. Plain return types produce status 200 and an empty `errors`
array. Methods are uppercase `GET`, `POST`,
`PUT`, `PATCH`, or `DELETE`. Error status codes are unique integers from 400
through 599. Each method and path pair and each operation `cpp_name` is unique.

Paths start with `/` and contain literal segments or whole-segment `{name}`
placeholders. Literals use ASCII letters, digits, `.`, `_`, `~`, and `-`.
A placeholder must name exactly one parameter of type `int` or `string`.
Parameters annotated `RIG_QUERY` after their C++ name have `"in": "query"`
in IR. Query parameters support scalar `int`, `bool`, and `std::string` values.
An `int` or `std::optional<int>` parameter can also carry
`RIG_RANGE(minimum, maximum)` after its name. Both bounds are inclusive
integer constants, with minimum no greater than maximum. The inspector emits
`"range": {"minimum": minimum, "maximum": maximum}` on that parameter.
OpenAPI adds the bounds to its integer schema, and generated dispatch rejects
out-of-range supplied values with HTTP 400 and `code: "invalid_request"`.
An omitted optional value passes without a range check.
`std::optional<T>` for one of these scalars makes it omittable: dispatch passes
`std::nullopt`, and OpenAPI sets `required` to false with the scalar schema.
Other parameters form the JSON request body; at most one is allowed. For
example, `list_items(std::optional<int> limit RIG_QUERY)` accepts both `/items`
and `/items?limit=10`. `GET` and `DELETE` cannot have a body under the current
convention.
These rules are shared by OpenAPI and the C++20 HTTP dispatch generator.
For the same method, literal segments take precedence over placeholders, and
integer placeholders take precedence over string placeholders. Parameterized
paths with the same shape, such as `/items/{id}` and `/items/{slug}`, are
rejected. Routes whose match sets overlap without a consistent specificity
order are also rejected. For example, `/{group}/fixed` and `/known/{item}`
both match `/known/fixed` when their placeholders are strings. Generated
dispatch uses the same precedence independently of declaration order.

Record fields are all present in JSON. An `optional` field is present with
either a value or `null`; it does not mean the field can be omitted. Successful
operations have a JSON response with HTTP 200. Unknown keys and unsupported
types are rejected so that every generator interprets version 6 the same way.
Older IR is rejected; regenerate it with `rig inspect` before running the
version 6 generators. `json-codec` and `http-routes` use `cpp_name` and no
longer take `--namespace`.

`RIG_SUMMARY`, `RIG_DESCRIPTION`, and `RIG_RESPONSE_DESCRIPTION` annotate an
operation with nonempty text. The first two become optional `summary` and
`description` strings in IR; the third becomes `response_description` for the
200 response. `RIG_BOOL_VALUE(true)` or `RIG_BOOL_VALUE(false)` on a bool
record field emits `bool_value` in IR. OpenAPI emits a single-value boolean
enum, and the JSON codec checks the value during both encoding and decoding.

The C++20 API uses `rig::result` in place of the earlier `RIG_ERROR` annotation.
The IR shape is unchanged: `returns` describes the success body, and `errors`
describes the status and body of each typed error alternative.

Generated dispatch matches the path without its query string. It decodes
percent escapes in string path parameters after matching path segments, so an
encoded slash stays within its parameter. A plus sign remains a plus sign.
Malformed percent escapes in a matched string parameter return HTTP 400.
For declared query parameters, dispatch decodes percent escapes and maps `+`
to space. Missing required values, duplicate names, or invalid values return
HTTP 400. Extra query parameters are ignored when their names are unique.

When a route converts a path or query parameter or decodes a JSON body, RIG
also declares an HTTP 400 response for invalid input. Its body has
`code` set to `invalid_request` and a string `message`. If the operation
declares its own 400 error, OpenAPI uses `anyOf` for both bodies. The generated
HTTP dispatcher returns this input error before invoking the application
function; exceptions thrown by the function remain application failures.
