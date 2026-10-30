# Request deadlines and streaming

[Documentation index](../README.md#documentation)

The [pure-ASGI middleware](../app/common/middleware/request_timeout.py) sends one JSON 408 before response headers, interrupts an incomplete stream after headers, and suppresses late responses after abandonment. It tracks downstream cleanup and shares request activity with mutation owners.

## Deadline contract

| Boundary             | Default    | Behavior                                                                                   |
| -------------------- | ---------- | ------------------------------------------------------------------------------------------ |
| `total_timeout`      | 10 seconds | From timeout-middleware entry until the final response body is successfully sent           |
| `first_body_timeout` | 5 seconds  | Maximum wait for the first requested body message                                          |
| `chunk_timeout`      | 2 seconds  | Maximum wait for each subsequent requested body message until the request body is complete |

Constructor budgets must be finite and greater than zero; invalid values fail
middleware construction. The overall deadline applies when the handler never reads
a body. Body-receive deadlines do not apply to the disconnect wait after the final
request-body message.

Application settings provide optional environment overrides:
`REQUEST_TIMEOUT_MS=10000`, `REQUEST_FIRST_BODY_TIMEOUT_MS=5000`, and
`REQUEST_CHUNK_TIMEOUT_MS=2000`. Milliseconds convert to seconds at middleware
construction. Both body-wait budgets must not exceed the total. See
[HTTP configuration](http-policy.md) for ranges, defaults, and source precedence.

ASGI receives a scope after HTTP headers have been parsed. `first_body_timeout` is
a body-message deadline, not slow-header protection. Server/ingress header-receive
protection requires separate configuration. The response deadline starts at timeout
middleware entry, not TCP acceptance, and does not cover outer middleware rejections.

## Response and error behavior

- Normal completion retires the response deadline. Dependency/background cleanup after the final response body does not change an already-completed response.
- Expiry before headers returns exactly one 408 with the `{ status, message, timestamp }` envelope. Total expiry uses `Total request timeout exceeded.`; body waits identify first-body or chunk expiry.
- Expiry after headers raises a dedicated internal stream-abort error. Uvicorn closes the incomplete HTTP response; there is no replacement JSON/408 and no synthetic final chunk that would falsely mark the stream complete. A client can observe its original status and partial bytes followed by an incomplete-body/connection error. Uvicorn/the outer error boundary may log the exception even though the wire contains no 500 response.
- Late sends are suppressed after expiry, disconnect, or response completion. Downstream exceptions, including unrelated `TimeoutError`, follow normal exception handling. External server cancellation propagates rather than being converted to 408.
- Explicit ASGI disconnects and transport `OSError` close the sending boundary and mark the request abandoned. Unmarked handlers receive cooperative cancellation; owned mutations retain their task until transaction cleanup settles. A receive-side `TimeoutError` is preserved, since its being an `OSError` subclass does not establish client disconnection.

## Body ownership and backpressure

One reader owns the server's receive channel and passes messages to the handler in order. Prefetch is bounded to one queued message and one in-flight message; the middleware does not accumulate an entire upload. Once the complete request has arrived, that reader can observe disconnects even if an ordinary handler never calls `receive()`.

For an ignored, incomplete multi-chunk upload, prefetch backpressure can delay disconnect observation until body messages are consumed. The middleware does not drain/discard arbitrary uploads to look for a disconnect; the overall response deadline still bounds the sending window. Other body-size and server receive policies retain their own responsibilities.

## Cancellation and cleanup limits

The response deadline can finish the transport before owned mutation work or cancellation-resistant work settles. Middleware retains unfinished downstream tasks and retrieves late failures. Expected request-expiry rejection does not produce an additional late-failure error record; unexpected late failures retain safe diagnostics. It does not cancel the same task again merely because cleanup is still running.

Cancellation is cooperative. It cannot force a blocked event loop, stop synchronous thread work, prove SQL cancellation, or guarantee rollback. Async resource owners must make cleanup cancellation-safe. In Starlette's AnyIO streaming cancel scopes, cleanup awaits may require a shielded cancel scope; arbitrary unshielded async generator cleanup cannot be guaranteed to finish by this middleware.

Retained tasks participate in [graceful shutdown](shutdown.md). Marked mutation
routes use the separate [transaction owner](transactions.md) through response
preparation and commit, checking activity before work, after delayed acquisition,
and immediately before commit. Successful delivery of a 408 does not establish
whether a concurrent mutation committed. An already-started COMMIT can succeed;
the transaction guide defines these uncertainty boundaries and retry limitations.

## Verification

[Unit checks](../tests/unit/middleware/test_request_timeout.py) cover response state, normal completion beyond the cleanup deadline, owned versus downstream timeouts, body delivery/backpressure, disconnect/transport failures, external cancellation, and cancellation-resistant late work.

[Loopback Uvicorn tests](../tests/integration/middleware/test_timeout_server.py) use the real application middleware stack and both `h11` and `httptools`. They verify pre-header 408 delivery before cleanup finishes, truncated streams without replacement responses, disconnect cleanup for ordinary handlers and stream generators, stalled-body JSON 408 behavior, and keep-alive reuse after earlier deadlines. Endpoints and listeners exist only in tests. These are HTTP tests; their fixture disables WebSockets and database lifespan startup.

```sh
python -m pytest -q --no-cov tests/unit/middleware/test_request_timeout.py tests/integration/middleware/test_timeout_server.py tests/integration/errors/test_middleware_rejections.py
```

See [Verification](verification.md) for current execution results and [Testing](testing.md) for the complete gates.
