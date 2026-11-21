# reader pass, gpt-5.6-sol

I checked the post against AWS documentation, the pinned `bedrock-agentcore` 1.24.0 source implied by post 07, OpenTelemetry, and Uvicorn documentation.

## 1. Claims that are wrong

- **Application status codes are not preserved for normal Runtime invocations.** The post says returning a Starlette response is how `401`, `413`, `503`, and `502` refusals reach the client. Through `InvokeAgentRuntime`, however, any container `4xx` or `5xx` becomes **HTTP 424 `RuntimeClientError`**. This also means the proposed busy `503` does not retain its normal retry semantics. Application status/body pass-through applies to session endpoints, not the ordinary invocation API. ([docs.aws.amazon.com](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-http-protocol-contract.html))

- **The middleware is not a reliable 2 MiB body limit.** It checks only the declared `Content-Length`, then lets Starlette read the stream. Uvicorn ignores `Content-Length` when `Transfer-Encoding` is present, so a chunked body accompanied by a small `Content-Length` can bypass this check; a legitimate chunked request without `Content-Length` is rejected. A real ASGI limit must count bytes while wrapping `receive()`. ([github.com](https://github.com/Kludex/uvicorn/blob/main/docs/server-behavior.md?utm_source=openai))

- **“Two things the hand-written server did” omits its read timeout.** Post 07’s server sets a 30-second socket timeout specifically so an incomplete body cannot occupy an admitted slot indefinitely. The replacement shown has no corresponding body-read timeout; Uvicorn’s documented default timeout is only for idle keep-alive periods between requests. ([raw.githubusercontent.com](https://raw.githubusercontent.com/levantar-ai/demos/main/agentcore/07-observability/agent/main.py))

- **The plain-`python main.py` tracing note is misleading.** Without `opentelemetry-instrument`, auto-instrumentation does not load the distro, configurators, or instrumentors. Unless some other code configures an OTel provider/exporter, Strands’ tracer is a no-op—not merely a separate trace. ([github.com](https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/opentelemetry-instrumentation/src/opentelemetry/instrumentation/auto_instrumentation/__init__.py))

## 2. Claims stronger than the post’s evidence supports

- **“The runtime sends the session id in baggage” is not a documented contract.** AWS documents `runtimeSessionId` and `baggage` as separate invocation inputs and instructs callers to put `session.id` into baggage when they need it propagated. The live observation may be valid for this deployment, but the post should either capture the incoming baggage header or retain a fallback that derives it from `context.session_id`. ([docs.aws.amazon.com](https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_InvokeAgentRuntime.html?utm_source=openai))

- **The Logs Insights query cannot prove that no span lacks `session.id`.** It filters to spans already having that value and then counts them. To prove completeness, first identify the trace IDs, then query *all* spans in those traces and count missing or mismatched attributes. It also examines only the runtime’s `spans` stream, not the spans stored for downstream services.

- **“Nothing the agent does changes” is only shown for the happy path.** Invalid JSON, exception responses, admission errors, slow uploads, and client-visible status handling all change. The demonstrated answer establishes business-output equivalence, not HTTP-contract equivalence.

- **Port 8080 and `/invocations` are defaults, not the immutable Runtime contract.** Runtime now permits a configurable serving port and invocation path. The statement is correct for this Terraform configuration but too general as written. ([docs.aws.amazon.com](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-http-protocol-contract.html))

## 3. Reproduction traps

- **The second parameter must literally be named `context`.** SDK 1.24.0 decides whether to pass context by inspecting whether parameter two is named `"context"`. Renaming it to `ctx` causes the handler to be called with only the payload. This non-obvious requirement should be stated. ([raw.githubusercontent.com](https://raw.githubusercontent.com/aws/bedrock-agentcore-sdk-python/v1.24.0/src/bedrock_agentcore/runtime/app.py))

- Tests made directly against port 8080 will observe `401/413/503/502`; deployed tests through `InvokeAgentRuntime` will instead observe `424 RuntimeClientError`.

- Chunked local requests will receive `413`, and a slow/incomplete upload can hold one of the eight semaphore slots until the client, proxy, or Runtime timeout intervenes.

- The tracing result depends on exact package/startup configuration. Post 07 pins `bedrock-agentcore==1.24.0`; the current release is newer, while the package still identifies itself as alpha. Reproducers should use the repository lock/pins rather than an unconstrained install. ([pypi.org](https://pypi.org/project/bedrock-agentcore/1.24.0/?utm_source=openai))

## 4. Production gaps — scope, not defects

- **Scope:** The semaphore is process-local and effectively session-local because Runtime sessions use isolated microVMs. It is not fleet-wide admission control; production still needs caller-side throttling, account-quota handling, and load shedding. Runtime V2 can accept hundreds of concurrent connections per session. ([docs.aws.amazon.com](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html?utm_source=openai))

- **Scope:** Production error handling needs a defined external error envelope, correlation ID, retry policy, idempotency rules, and separation of retryable upstream failures from permanent client errors. Collapsing everything into an application `502`, which becomes Runtime `424`, removes that distinction. AWS treats `424` as non-retryable while platform `429/503` errors are retry candidates. ([docs.aws.amazon.com](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/disaster-recovery-operate.html?utm_source=openai))

- **Scope:** No discussion of graceful shutdown/resource cleanup, cancellation, dependency timeouts, streaming responses, or background tasks.

- **Scope:** Trace-content redaction, access control, retention, sampling cost, and secret handling are inherited from post 07 rather than revisited.

- **Scope:** A production migration would regression-test both the direct ASGI server and the managed invocation surface, especially malformed bodies, overload, timeouts, and trace continuity.

## 5. Drift or unnecessary detail

- The full order answer and tool trail in section 4 are longer than needed for a server migration; a compact smoke response plus the trace relationship would suffice.
- The class-replacement/subclassing explanation of Starlette instrumentation is technically relevant but too implementation-specific and brittle for the main narrative. It could be reduced to: auto-instrumentation wraps Starlette before the application is imported.
- The conclusion largely repeats the TL;DR and section 3.

**Verdict: Sound SDK migration and tracing demonstration, but the client-visible error semantics, body-limit implementation, and lost read timeout need correction before publication.**
