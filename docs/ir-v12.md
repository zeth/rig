# RIG IR version 12

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
  "ir_version": 12,
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
      "result": true,
      "errors": [
        {"status": 404, "type": {"kind": "named", "name": "app::Error"}}
      ]
    }
  ]
}
```

The top level has `ir_version`, `types`, and `operations`, plus optional
`service` metadata. A type is a
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
| `builtin` | `name`: `int`, `int64`, `double`, `bool`, or `string` | C++ `int`, `long long`, `double`, `bool`, or `std::string` |
| `named` | `name`: a declared qualified C++ type name | Record or enum |
| `array` | `items`: a type reference | `std::vector<T>` |
| `optional` | `value`: a type reference | `std::optional<T>` |

An operation has `name`, `cpp_name`, `method`, `path`, `parameters`, and `returns`.
The inspector writes `result: true` for a `rig::result` return type and
`result: false` for a plain return type. A documented server-level error can
therefore coexist with a plain function return.
`errors` is an optional ordered array of `{status, type}` objects; the
inspector writes it even when empty. A function returning `rig::result<Success,
rig::error<Status, Body>...>` supplies both the success type and its declared
error responses. The generated HTTP dispatcher returns the selected status
and encoded body. Plain return types produce status 200; their `errors` array
can document responses supplied by the hosting server. An annotated error
can carry `exceptions`, a nonempty array of qualified C++ class names written
by `RIG_ERROR_RESPONSE(status, Body, description, Exception...)`. Each name
appears at most once per operation. Generated dispatch catches them in IR
order and returns the error's status with
`rig_error_body(std::type_identity<Body>{}, status, exception)`, a function
the application supplies for argument-dependent lookup. The inspector rejects
a mapped type listed after one of its bases. OpenAPI ignores `exceptions`.
Methods are uppercase `GET`, `POST`,
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
`RIG_INT_VALUES(...)` declares one to sixteen allowed `int` values for an
`int` or `std::optional<int>` parameter. The inspector emits `int_values` in
IR; OpenAPI emits an integer `enum`, and generated dispatch rejects other
values with HTTP 400. It cannot be combined with `RIG_RANGE`.
`RIG_PARAMETER_DESCRIPTION(text)` adds a nonempty path or query parameter
description to the IR and OpenAPI output.
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

Record fields are present in JSON unless marked `RIG_OMIT_EMPTY`. A plain
`optional` field is present with either a value or `null`. `RIG_NULLABLE` on an
optional primitive field produces a required property with a primitive `type`
union that includes `null`. `RIG_OMIT_EMPTY` allows an optional field to be
absent when it has no value, and OpenAPI excludes it from `required`. The two
annotations can be combined on `std::optional<std::optional<T>>`: the outer
optional controls omission and the inner optional controls `null`. Successful
operations have a JSON response with HTTP 200. Unknown keys and unsupported
types are rejected so that every generator interprets version 12 the same way.
Older IR is rejected; regenerate it with `rig inspect` before running the
version 12 generators. `json-codec` and `http-routes` use `cpp_name` and no
longer take `--namespace`.

`RIG_SUMMARY`, `RIG_DESCRIPTION`, and `RIG_RESPONSE_DESCRIPTION` annotate an
operation with nonempty text. The first two become optional `summary` and
`description` strings in IR; the third becomes `response_description` for the
200 response. `RIG_BOOL_VALUE(true)` or `RIG_BOOL_VALUE(false)` on a bool
record field emits `bool_value` in IR. OpenAPI emits a single-value boolean
enum, and the JSON codec checks the value during both encoding and decoding.

`RIG_FIELD_DESCRIPTION(text)` and `RIG_MINIMUM(value)` annotate record fields.
The latter requires an `int` field. Both appear in the field IR and its OpenAPI
property schema. `RIG_STRING_VALUES(...)` limits a string field (or an
omittable optional string field) to one of up to sixteen nonempty values. The
JSON codec checks the values in both directions, and OpenAPI emits a string
`enum`. A described reference field uses `allOf` around its reference so the
description remains beside it. A `RIG_CONTEXT` parameter is supplied by the
hosting server, so it is listed with its name and zero-based position in `context_parameters`
rather than HTTP `parameters`. OpenAPI ignores it. The generated HTTP
dispatcher accepts a context object and reads members with matching names,
preserving the original C++ argument order. The hosting server can translate
decoding failures returned by generated dispatch; each response carries the
matched operation's IR name so the host can apply its error policy. OpenAPI does not add a
synthetic invalid-request response for these operations.

`RIG_INLINE_RECORD` marks a C++ record whose OpenAPI object schema appears at
each use site instead of in `components.schemas`. It does not change generated
JSON codecs or C++ types. Combine it with `RIG_OPEN_RECORD` when the inline
object permits additional properties in the control contract.

`RIG_ERROR_RESPONSE(status, Body, "Description")` declares an additional
HTTP error response supplied outside the function, such as by authentication
middleware. RIG reflects the C++ body type and includes it among reachable
schemas. The IR error entry includes its status, type, and description. These
responses do not change the function's C++ return type or generated dispatcher;
the surrounding HTTP server remains responsible for returning them.

`RIG_OPEN_RECORD` on a C++ record emits `"open": true` in IR. OpenAPI leaves
`additionalProperties` unspecified for that record; the C++ codec accepts
unknown JSON fields when decoding it. Other records remain closed.
`rig openapi --omit-operation-ids` suppresses inferred operation IDs when an
existing contract relies on path-based client naming; inferred IDs remain the
default.

`RIG_API(title, version)` on an empty C++ service record marks it for namespace
discovery. Repeated `RIG_SERVER(url)` annotations list the advertised server
URLs, and one `RIG_BEARER_AUTH(name, format)` declares a global HTTP bearer
scheme. The inspector emits these as a `service` object with `title`,
`version`, `servers`, and optional `bearer_auth` and `validation_error`. OpenAPI uses them for `info`,
`servers`, `components.securitySchemes`, and global `security`. Without a
service declaration, `rig openapi` continues to use its title and version
arguments and emits no servers or security scheme. A namespace registration
can discover at most one service declaration.

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
Server-supplied context parameters do not affect this rule: an operation with
any path, query, or body parameter can return the 400.

`RIG_VALIDATION_ERROR(Body, description)` on the service record replaces that
body. The inspector emits `service.validation_error` with the body's `type`
and nonempty `description`, and registers the body type. Generated dispatch
then builds the 400 body with
`rig_error_body(std::type_identity<Body>{}, 400, exception)`, passing the
decoding exception, and OpenAPI omits `RigInvalidRequest`. An operation without
a 400 gets one with the configured description and body; one that already
declares a 400 with the same body keeps it, and a different body uses `anyOf`.
A missing required record field fails decoding with the message `missing`
followed by the field name.
