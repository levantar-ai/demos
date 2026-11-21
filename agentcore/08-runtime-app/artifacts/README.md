# Deployment artifacts, captured from a real run

Captured from the deploy and invoke cycle of this demo in `us-east-1`,
policy engine in `ENFORCE`, Transaction Search already on in the account
from demo 07.

## What was deployed

- `terraform apply` added 76 resources in one pass, with image `63fdeeb`,
  the first port. Its `pip install` line was demo 07's, so the build
  reused that layer.
- Image `d82d5a1` replaced it after the review below, the commit the
  agent's code was last changed in. It pins `starlette==1.10.0` and
  `uvicorn==0.54.0`, the versions `pip freeze` showed in `63fdeeb`. The
  same apply replaced the exchange's service user password. The run and
  the video below are on this image.
- Runtime `demos_agentcore_08_runtime_app-7z6lIhGqpQ`, log group
  `/aws/bedrock-agentcore/runtimes/demos_agentcore_08_runtime_app-7z6lIhGqpQ-DEFAULT`.

## Live run

Customer `c-1000`, password generated in memory for the run and never
written down. One conversation, the spending question then the carrier
question, after three requests that should be refused.

| Request | Result |
|---|---|
| No token | 401 from the runtime, `Missing Authentication Token`. It never reaches the container |
| Blank prompt, valid token | The agent's 400, returned to the client as the runtime's 424 `Received error (400) from runtime` |
| Body that is not JSON, valid token | The SDK's 400, returned the same way |
| Spending by month | 200. Trail `orders___list_orders`, `run_python`, restated once by the figure check. January £250.00, February £310.50, June £70.00, July £113.30, total £743.80 |
| Most used carrier | 200. Trail `run_python`. DPD 6 orders, Royal Mail 3 |

The same five requests on `63fdeeb` gave the same statuses and figures.

## What the traces showed

Logs Insights over the runtime's `spans` stream, filtered by the
conversation's session id.

| Trace | Spans | What it is |
|---|---|---|
| `6b015f451fa5d85d54880d7d4466490b` | 46 | Turn 1 |
| `6b015f5b17f98a264b2eb19c67e4ca3c` | 29 | Turn 2 |
| `6b015f444a7d8c596a6017e17a676515` | 1 | Refused request, 400 |
| `6b015f4301387ac35efa0cfa34dc6593` | 1 | Refused request, 400 |

- No span in those traces is without `attributes.session.id`. A second
  query, `traceId in [...] and not ispresent(attributes.session.id)`,
  returned nothing.
- Each trace's `POST /invocations` span is kind `SERVER` with a parent span
  id that is not in the container's stream, the runtime's own span.
- `aws/spans` holds the gateway's and the memory's spans under the same
  trace ids. Turn 1 has `AgentCore.Policy.AuthorizeAction`,
  `AgentCore.Gateway.InvokeTool.orders___list_orders`, the orders Lambda,
  `CreateEvent`, `ListEvents` and `RetrieveMemoryRecords`. Turn 2 called no
  gateway tool and has the memory's spans and the gateway's tool listing.

## Where the session id comes from

Demo 07's `traced()` set `session.id` in the baggage itself, so that run
could not show whether the runtime sends it. A diagnostic image (tag
`diag-1`, the same code with one `print` of the request's baggage keys and
trace header names) was deployed once and replaced before the run above. Every request printed baggage keys `Self` and `session.id` and
one trace header, `x-amzn-trace-id`. So the runtime sends the session id in
the baggage and its trace context in X-Ray's header, and ADOT reads both.

## Checked in the package source

- `bedrock_agentcore/runtime/app.py` is byte-identical in 1.24.0, the
  version pinned here, and 1.27.0, the newest on PyPI when this was built.
- Under `opentelemetry-instrument`, `BedrockAgentCoreApp.__mro__` is
  `BedrockAgentCoreApp`, `_InstrumentedStarlette`, `Starlette`, and a new
  app has `OpenTelemetryMiddleware` in its middleware.
- The SDK sets no `session.id` baggage of its own. Its span processor
  stamps only the routing experiment attributes.

## Review, gpt-5.6-sol

`scripts/review-post.py`, both passes, on the first port (`63fdeeb`).

Acted on:

- The post said what a client is told when a turn fails. Through the
  runtime a client is told 424 whatever the container answers, which this
  run had already shown for a 400. The post now says the runtime reports
  any error status as its own 424, and gives the real reason to catch an
  exception, that the SDK logs it with its traceback and returns its
  message.
- The body bound trusted `Content-Length`. Sent with `Transfer-Encoding`
  as well, the server frames by the encoding. The middleware now refuses
  any request with `Transfer-Encoding`, with a test.
- Demo 07's 30 second socket timeout had been dropped with the server. A
  stalled body would have held one of the eight slots. `timely()` restores
  it, with a test that a longer turn is not cut off.
- The agent now imports Starlette directly, so it and uvicorn are pinned.
  The Dockerfile and README say the six packages are pinned by version and
  their dependencies are not locked.
- `random_password` for the exchange's service user did not guarantee a
  digit, which the pool's policy requires, about a 3% chance of a failed
  apply. It has explicit minima now.
- The NOTE about starting with plain `python main.py` was wrong, without
  ADOT there are no spans at all. Removed, and the explanation of how ADOT
  instruments the app cut to a sentence, the detail is in the README.
- "The runtime sends the session id in baggage" is now stated as observed
  on this deployment and not documented by AWS.
- The post's port and paths are described as the runtime's defaults.
- A NOTE that the entrypoint's second parameter must be named `context`.
- Section 4's answer and the conclusion shortened.

Recorded, not acted on:

- The exchange puts the customer's token in Cognito `ClientMetadata`, and
  order authorisation is keyed by the reusable username. Both are demo
  05's design, described there, and not changed by this post.
- Production scope the reader pass listed: fleet-wide admission control, a
  defined error envelope and retry policy, graceful shutdown, streaming.
