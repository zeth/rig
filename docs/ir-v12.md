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
| `builtin` | `name`: `int`, `int64`, `double`, `bool`, `string`, or `object` | C++ `int`, `long long`, `double`, `bool`, `std::string`, or `nlohmann::json` |
| `named` | `name`: a declared qualified C++ type name | Record or enum |
| `array` | `items`: a type reference | `std::vector<T>` |
| `optional` | `value`: a type reference | `std::optional<T>` |
| `map` | `values`: a type reference | `std::map<std::string, T>` |
| `variant` | `alternatives`: two or more distinct, non-optional type references | `std::variant<T...>` |

An operation has `name`, `cpp_name`, `method`, `path`, `parameters`, and `returns`.
The inspector writes `result: true` for a `rig::result` return type and
`result: false` for a plain return type. A documented server-level error can
therefore coexist with a plain function return. For a `rig::success<Body>`
return, `returns` is `Body` and the inspector writes `chosen_status: true`.
Such an operation is generated, has `result: false`, and lists its other
statuses in `success_responses` (from `RIG_SUCCESS_RESPONSE`). Generated
dispatch answers with the status the function returned, after checking it is
the operation's `success_status` (200 by default) or one of those; any other
status is an internal error.
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
in IR. Query parameters support scalar `int`, `long long`, `bool`, and `std::string` values.
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
and `/items?limit=10`. `GET` cannot have a body.
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
operations have a JSON response with HTTP 200, or with the status from
`RIG_SUCCESS_STATUS(status)`, emitted as `success_status`: a 2xx status other
than 204 or 205, since every success response has a body.

Fields and HTTP parameters share four constraints. `RIG_FORMAT(name)` emits
`format` on a string or integer, such as `uuid`, `date` or `int32`; OpenAPI
documents it and generated code does not yet enforce it. `RIG_MIN_LENGTH(n)`
and `RIG_MAX_LENGTH(n)` emit `min_length` and `max_length` on a string, which
OpenAPI documents as `minLength` and `maxLength` and generated decoding
enforces with HTTP 400. `RIG_DEFAULT(value)` emits `default`, a boolean,
integer or string matching the value type. A defaulted field is not optional
in C++ but is not required in JSON: decoding fills in the default. A
defaulted query parameter likewise has a non-optional C++ type, is not
required in OpenAPI, and receives the default when the request omits it.
`RIG_STRING_VALUES(...)` on a string path or query parameter emits
`string_values`, and `RIG_MINIMUM(value)` on an `int` parameter emits a
one-sided `minimum`; both are enforced like `RIG_RANGE` and `RIG_INT_VALUES`.

A body parameter of type `std::optional<T>` makes the request body optional:
OpenAPI sets `required: false`, and an empty body decodes to `std::nullopt`.
A GET never has a body.

`RIG_DESCRIPTION(text)` on a record emits its `description`, which OpenAPI
puts on the record's schema.

`RIG_MIN_PROPERTIES(n)` on a record emits `min_properties`; OpenAPI documents
`minProperties` and decoding rejects an object with fewer members, which suits
partial updates that must change something.

OpenAPI writes an optional value as its schema with `null` added to its
`type`, as OpenAPI 3.1 and 3.2 do, and an optional reference as `anyOf` the
reference and null.

`RIG_NULLABLE` with `RIG_STRING_VALUES` gives a string that may also be null:
OpenAPI adds `null` to the enum. `RIG_OMIT_EMPTY` with `RIG_NULLABLE` on
`std::optional<std::optional<T>>` also accepts a record or array `T`, which
OpenAPI documents as `anyOf` the type and null; a required nullable record is
just a plain `std::optional`.

`RIG_PATTERN(regex)` on a string field or parameter emits `pattern`, which
OpenAPI documents and generated decoding enforces as an unanchored ECMAScript
search, as JSON Schema does.

`RIG_VALUE_TYPE` on a record with exactly one required field emits
`"value": true`. The record is its field on the wire, so a named schema need
not be an object: a constrained string or a map, for example. OpenAPI emits
the field's schema with its constraints and the record's description, and the
codec encodes and decodes the field, checking its constraints. A value type
whose field is a scalar can be a query parameter, decoded through the codec.

A `variant` is OpenAPI's `oneOf`. Decoding tries every alternative and
accepts the value only when exactly one alternative accepts it, so input that
matches none or several fails with HTTP 400; encoding writes the held
alternative. A query parameter may be a variant when every alternative
decodes from a string. Value types may be `RIG_INLINE_RECORD`, so a variant can
list constrained strings inline, as `oneOf` alternatives usually are.

A record with one base class emits `base`, the base record's qualified name,
and lists only its own fields. OpenAPI emits `allOf` with a reference to the
base and an object schema of the record's own fields. The codec encodes the
base first, and decodes the base from the members the record does not add.
Base records must be registered, non-value records, may not form a cycle, and
may not share a field name with a record that extends them.

`RIG_WRITE_ONLY` on a field emits `"write_only": true`, and OpenAPI marks the
property `writeOnly`: clients send it, and responses never contain it. A record
schema lists `required` only when some field is required. `RIG_MINIMUM(value)`
applies to an `int` field or an omittable `std::optional<int>` field.

The `object` builtin is a free-form JSON object: OpenAPI emits `type: object`
with `additionalProperties: true`, and the codec accepts any object. The
inspector recognises `nlohmann::json` by shape, without including nlohmann; a
`basic_json` with a different object type, such as `nlohmann::ordered_json`,
is unsupported. A `map` is a JSON object whose member values share one type;
OpenAPI emits `additionalProperties` with that type's schema. Any other
template specialisation is unsupported and rejected. Unknown keys and unsupported
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
`version`, `servers`, and optional `bearer_auth`, `validation_error`,
`unauthorized`, `internal_error`, and `method_not_allowed`. OpenAPI uses them for `info`,
`servers`, `components.securitySchemes`, and global `security`. Without a
service declaration, `rig openapi` continues to use its title and version
arguments and emits no servers or security scheme. A namespace registration
can discover at most one service declaration.

`RIG_UNAUTHORIZED(Body, description)` on a service with bearer auth emits
`service.unauthorized` with the body's `type` and nonempty `description`, and
registers the body type. OpenAPI then documents a 401 response with that body
on every operation except those marked `RIG_PUBLIC`. Such an operation cannot
also declare its own 401. `RIG_PUBLIC` on an operation emits `"public": true`,
requires service bearer auth, and produces `security: []` in OpenAPI. Both
annotations describe authentication rather than perform it. Generated
dispatch provides `rig_http::is_public(method, path)`, which applies the same
route precedence as `dispatch` and returns whether the operation it would
select is public, so the hosting server can skip authentication for exactly
those operations.

`RIG_INTERNAL_ERROR(Body, description)` on the service emits
`service.internal_error` and registers the body type. Generated dispatch then
catches `std::exception` from every operation after its mapped exceptions and
returns 500 with `rig_error_body(std::type_identity<Body>{}, 500, exception)`;
an operation that already maps `std::exception` keeps its own mapping. OpenAPI
documents the 500 on every operation, keeping a declared 500 with the same body
and using `anyOf` for a different one. Exceptions not derived from
`std::exception` still propagate to the hosting server.

`RIG_METHOD_NOT_ALLOWED(Body, description)` on the service emits
`service.method_not_allowed` and registers the body type. When no operation
takes a request, generated dispatch then checks whether its path matches any
declared operation, including host-response operations. If it does, dispatch
returns 405 with `rig_error_body(std::type_identity<Body>{}, 405, error)`,
where `error` is a `rig_http::method_not_allowed`, and sets the response's
`allow` to the matching operations' methods in sorted order, separated by
`", "`, for the host to send as the `Allow` header. A path that matches no
operation still returns no response. OpenAPI does not document the 405: a
request with an operation's own method never receives it. Without the
annotation, dispatch returns no response for an unmatched method, as before.
`allow` is empty on every other response.

`RIG_HOST_RESPONSE(media_type)` marks an operation whose response the hosting
server writes, with that media type, or a media range such as `*/*` or `text/*`
when it serves several. The declaration describes the contract and need not be
defined. The inspector emits `host_response`; a media type
other than `application/json` requires a `std::string` return. Such an
operation has no context parameters and maps no exceptions. Generated dispatch
still ranks its route with the others and returns no match when it is selected,
so a less specific generated route never takes its requests; `is_public`
includes it. `rig_http::is_host_served(method, path)` applies the same route
precedence and returns whether the operation dispatch would select is a
host-response operation. A host that runs its own handlers only when it returns
true serves exactly the routes the contract declares: when dispatch returns no
response and `is_host_served` is false, the request names no operation. A host-response operation can describe its response further:
`RIG_STRING_VALUES(...)` on the operation emits `response_values`, the strings
a string response may be; `RIG_FORMAT(name)` emits `response_format`, such as
`binary`, for which OpenAPI describes the response by its media type alone, with
no schema; and each `RIG_SUCCESS_RESPONSE(status, description)` emits an entry
in `success_responses`, another 2xx status with the same body, for a host that
chooses the status at run time. A `text/event-stream` operation may also list
204, which has no body: answering a reconnect with 204 tells the client the
stream is finished and it should stop reconnecting. Outside host responses, only a `chosen_status`
operation has `success_responses`.

`RIG_RESPONSE_MEDIA_TYPE(media_type)` on a generated operation that returns a
string emits `media_type`, a concrete media type other than `application/json`,
such as `text/plain` or `application/yaml`.
OpenAPI documents the success response under that media type with a string
schema, which `RIG_STRING_VALUES(...)` on the operation can limit as
`response_values`. Generated dispatch returns the string as the response's JSON
`body` and sets the response's `media_type`, which is `application/json` for
every other operation, so the host writes the string as text.

A host-response operation that returns `rig::host_value` instead of a string
emits `"host_value": true`. Generated dispatch then calls it like any generated
operation: it decodes the parameters, passes context, and maps exceptions to
their declared errors. The operation returns the status it chose, 200 or one of
its `success_responses` (any other is the service's internal error), and a
`std::any` holding whatever the host needs to write the body, such as a function
that streams it. Dispatch returns them as the response's `status` and `host`,
with no JSON body, and `is_host_served` answers false for the operation.

`RIG_HEADER(name)` on a string parameter makes it a request header, emitted
with `"in": "header"` and the header's `name`, which need not be a C++
identifier, such as `Last-Event-ID`. OpenAPI marks it required only when its
type is not optional. Generated dispatch takes an optional last argument, a
`rig_http::header_lookup` that returns a header's value by name, ignoring case,
or nothing when the request lacks it. Dispatch passes the value to the
operation, and a missing required header is a validation error. Without a
lookup, every header is missing.

Each `RIG_SSE_EVENT(name, Body)` on a `text/event-stream` host response emits an
entry in `sse_events`, and the body types are reachable like any other. OpenAPI
documents the stream with the media type's `itemSchema`, which describes each
event (`event`, `data`, `id` and `retry`): one `oneOf` alternative per declared
event, fixing `event` to its name and describing `data` as JSON whose
`contentSchema` is the body. A stream without declared events allows any event.

`rig json-codec` also writes `rig_events::<name>(const Body&)` for each declared
event, returning a `rig::event<nlohmann::json>` with the event's name and its
encoded body. The function name is the event name with every character outside
`[A-Za-z0-9_]` replaced by `_`, a leading `_` before a digit, and a trailing `_`
after a C++ keyword, so `card.changed` becomes `card_changed`. An event name
declared with several body types gets one overload per type, and two names that
would need the same function for the same type are an error. A server that
builds its events only with these functions can send no undeclared name, and no
name with another event's data.

`rig openapi` writes JSON, or YAML with `--format yaml`, in an order that does
not depend on where declarations live: paths and schemas sorted by name,
methods and operation keys in OpenAPI's usual order, responses by status. The
same IR therefore always gives the same bytes.

Each `RIG_RESPONSE_HEADER(name, description)` on a host-response operation
emits an entry in `response_headers`, which OpenAPI documents as a string
header on its success responses.

`RIG_OPERATION_ID(name)` on any operation emits `operation_id`. OpenAPI uses it
as the `operationId`, even with `--omit-operation-ids`, which then omits only
the generated ones. OpenAPI documents its success response with that media type, its
parameters, declared errors and the service 401, but not the generated 400 or
500, because the generated dispatcher neither decodes nor calls it.

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
