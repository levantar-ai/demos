# Deployment artifacts, captured from a real run

Captured from the deploy and invoke cycle of this demo in `us-east-1`,
policy engine in `ENFORCE`, Transaction Search already on in the account
from demo 07.

## What was deployed

- Image `63fdeeb`, the commit the agent's code was last changed in. The
  `pip install` line is demo 07's, so the build reused its layer.
- `terraform apply` added 76 resources in one pass.
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
| Spending by month | 200. Trail `orders___list_orders`, `run_python`, `run_python`, restated once by the figure check. January £250.00, February £310.50, June £70.00, July £113.30, total £743.80 |
| Most used carrier | 200. Trail `run_python`. DPD 6 orders, Royal Mail 3 |

## What the traces showed

Logs Insights over the runtime's `spans` stream, filtered by the
conversation's session id.

| Trace | Spans | What it is |
|---|---|---|
| `6b015af52941018a6f55b7e36b61f178` | 53 | Turn 1 |
| `6b015b0862cfffc1197a9c8059395860` | 29 | Turn 2 |
| `6b015af41e44c18e2f629d8612a4060c` | 1 | Refused request, 400 |
| `6b015af323026c6b637fba2d48549fb1` | 1 | Refused request, 400 |

- No span in those traces is without `attributes.session.id`.
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
trace header names) was deployed once and replaced by `63fdeeb` before the
run above. Every request printed baggage keys `Self` and `session.id` and
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
