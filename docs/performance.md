# Runtime cost of generated code

Notes for later. Nothing here needs doing yet.

## Routing

Generated dispatch tries one `std::regex` per route, in precedence order, and
`is_public` walks the same order. Host-response operations take part too, so
a request the host serves still passes through the chain first.

Measured on 21 October 2026 with Holder's generated routes (77 routes, GCC
16.2.1, `-O2`, libstdc++'s `std::regex`):

| Request | Generated routing | Handwritten string compares |
| --- | --- | --- |
| A route late in the chain | about 7 µs | about 0.03 µs |
| A path that matches no route | about 5 µs | |
| The first route | about 0.1 µs | |

With `is_public` as well, that is roughly 10 µs per request at worst. A
request to a local daemon also parses HTTP, does socket I/O and usually
queries SQLite, which takes hundreds of microseconds to milliseconds, so this
is about 1% of a request and not worth changing yet.

If it ever matters, the fix belongs in the generator, not in applications.
RIG knows each route's exact shape: literal segments and `int` or string
placeholders. It does not need regexes. `http-routes` could instead emit a
matcher that splits the path once and branches on the method, the segment
count and the literal segments, like a trie, using the same precedence rules
as `ir.route_priority`. That should bring routing to tens or hundreds of
nanoseconds, below a hand-written chain of `if` statements over a hundred
routes. Applications would only regenerate their headers. `is_public` could
share the matcher, so a request is matched once for both questions.

To measure again, time `std::regex_match` over the patterns in a generated
routes header, for a path that matches late and one that matches nothing.

## JSON

Generated code fills a typed struct and then encodes it with nlohmann, where
hand-written code builds the nlohmann object directly. That is one extra small
struct per request. Building the `nlohmann::json` tree dominates either way.

## Compile time and size

`json-codec` emits a codec for every type an operation reaches, including
types only host-response operations use, which generated dispatch never
encodes or decodes. For Holder that is a 3,600-line codec header. It costs
compile time and binary size, not request time. If it grows awkward, the
generator could skip codecs for types reached only from host responses, and
add them back when an operation moves behind generated dispatch.
