# Moving an AgentCore agent onto the SDK's server

## TL;DR;

The order support agent from post 07 now serves its requests with
`BedrockAgentCoreApp`, the server in AWS's `bedrock-agentcore` Python SDK,
in place of the hand-written one the series has carried since post 01. The
agent becomes one function, the SDK serves the runtime's contract around
it, and the tracing code post 07 added is deleted, because a turn now joins
the runtime's trace without it. The SDK does not bound a request or keep an
error's detail from a client, so that part stays in the agent.

> SOURCE CODE - All code for this post is available at:
> https://github.com/levantar-ai/demos/tree/main/agentcore/08-runtime-app

## Longer version

This series is building one thing, the order support agent for Brightwell,
a small online retailer of outdoor kit. Post 01 wrote the agent's HTTP
server by hand on Python's standard library, to show how little AgentCore
Runtime asks of a container, which is `POST /invocations` and `GET /ping`
on port 8080. Seven posts later that server is still there, and post 07 had
to add tracing code to it that a web framework would have made unnecessary.

AWS ships a server for this contract in the `bedrock-agentcore` SDK,
`BedrockAgentCoreApp`. It is where the SDK's own quick start begins, so
expect to meet it in other people's agents. This post moves the agent onto
it and the rest of the series builds on that. Nothing the
agent does changes, and the Terraform is post 07's with the names changed.

![The agent of post 07 on the SDK's server, one function behind the runtime's contract](architecture.png)

## 1 - The agent as one function

The SDK has been in the image since post 06, where the agent took its
memory session manager from it, so the `pip install` line is unchanged. The
server is one import, and the function that handles a turn is registered
with a decorator:

```python
from bedrock_agentcore.runtime import BedrockAgentCoreApp

app = BedrockAgentCoreApp(middleware=[Middleware(Admitted)])


@app.entrypoint
def invoke(payload, context):
    headers = context.request_headers or {}
    customer = customer_from(headers)
    subject = subject_from(headers)
    if customer is None or subject is None:
        return refused(401, "no verified caller")
    ...
    session = session_from(context.session_id, payload)
    ...
    with one_turn(subject, session):
        gateway_token = exchange(bearer_from(headers))
        turn = respond(prompt, customer, session, gateway_token, subject)
    return bounded(turn)


if __name__ == "__main__":
    app.run(host="0.0.0.0")
```

The SDK parses the JSON body and passes it in as `payload`. `context` holds
what the runtime sent with the request, the session id from the runtime's
session header and the headers the runtime is configured to forward, which
for this agent is `Authorization`, as post 05 set up. The function returns
a dict and the SDK sends it as JSON, or it returns a Starlette response
when it wants a status code of its own, which is how the refusals are sent.

The SDK also answers `/ping`, and it runs the function on a worker thread,
so a turn that takes a while does not stop the health check being answered.

What is deleted is everything that was only there to be a server, the
request handler class, the routing on the path, reading the body by its
`Content-Length`, and writing the status line, the headers and the JSON of
each response.

> NOTE: `app.run()` listens on localhost unless it finds Docker's
> `/.dockerenv` file or a `DOCKER_CONTAINER` environment variable. The
> runtime has to reach the port, so name the host as above rather than
> leave it to the detection.

## 2 - The trace joins itself

Post 07 added a function, `traced()`, that read the trace context from the
request headers, put the session id in the baggage and attached both for
the length of the turn. It was needed
because ADOT, the AWS Distro for OpenTelemetry, instruments web frameworks
and the standard library's server is not one.

`BedrockAgentCoreApp` is a Starlette application, and Starlette is one of
the frameworks ADOT instruments. So `traced()` is deleted and nothing
replaces it. The start command from post 07 is what makes that work, and it
has not changed either:

```dockerfile
CMD ["opentelemetry-instrument", "python", "main.py"]
```

`opentelemetry-instrument` loads ADOT before any of the agent's code is
imported. ADOT replaces Starlette's application class with a subclass of
its own that adds tracing middleware, and the SDK's app then subclasses
that one. The middleware reads the runtime's headers and starts a span for
the request, and the SDK carries that context onto the worker thread the
function runs on. The runtime sends the session id in the request's
baggage, and ADOT copies it from there onto every span, so that needs no
code either.

> NOTE: this depends on the order. Start the container with plain
> `python main.py` and the app is built on the uninstrumented class, so the
> agent's spans form traces of their own again.

## 3 - What stays in the agent

The SDK passes the payload to the function unchanged, and the decorator's
own documentation says to validate it. The caller check, the prompt check and
the session check are the same lines as before.

Two things the hand-written server did are not things the SDK does. It
reads whatever body it is sent, and it has no limit of its own on the turns
in flight. The app's constructor accepts ASGI middleware, so the agent's
two bounds, a 2 MB body and eight turns at once, are applied before the SDK
reads anything:

```python
class Admitted:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        length = dict(scope["headers"]).get(b"content-length", b"")
        if not length.isdigit() or not 0 < int(length) <= MAX_BODY_BYTES:
            return await refused(413, "request body must be 1..2MB")(scope, receive, send)
        if not _turns_in_flight.acquire(blocking=False):
            busy = f"the agent is serving {MAX_TURNS_IN_FLIGHT} turns already; try again"
            return await refused(503, busy)(scope, receive, send)
        try:
            await self.app(scope, receive, send)
        finally:
            _turns_in_flight.release()
```

The other is what a client is told when a turn fails. An exception that
escapes the function is answered by the SDK with a 500 whose body is the
exception's message, and a message can carry a token, a response body or
the model's code. So the function catches everything, logs the exception's
class and answers with the same generic error as before:

```python
    except Exception as exc:
        print(f"turn failed for {customer}: {describe(exc)}")
        return refused(502, "request failed")
```

## 4 - The same turn, the same trace

Deployed, the agent answers as it did in post 07. The model lists the
customer's orders through the gateway and works the figures out in the
sandbox, and the response carries the trail:

```
  1. orders___list_orders  [success]
  2. run_python  [success]
  3. run_python  [success]

Looking at your orders, here's your spending with us this year (2026), month by month:

- January: £250.00
- February: £310.50
- June: £70.00
- July: £113.30

Your biggest month was February with £310.50, and your total for 2026 is £743.80.
```

The trace is the part worth checking, since the code that joined it is
gone. One Logs Insights query over the runtime's `spans` stream finds the
conversation by its session id and counts the spans of each trace:

```
filter @logStream = "spans" and `attributes.session.id` = "<session id>"
| stats count(*) as spans by traceId
```

```
traceId                           spans
6b015af52941018a6f55b7e36b61f178     53
6b015b0862cfffc1197a9c8059395860     29
6b015af41e44c18e2f629d8612a4060c      1
6b015af323026c6b637fba2d48549fb1      1
```

The first two are the conversation's two turns, each one trace, and no
span in either is missing the session id. The first span in the container
is now the request itself, `POST /invocations`, and its parent is the
runtime's span, so the turn sits under the runtime's trace as it did
before. The gateway's Cedar check, the orders Lambda and the memory join
the same trace, as in post 07.

The last two are requests that were refused with a 400, one by the agent
for a blank prompt and one by the SDK for a body that was not JSON. A
refusal is a trace of one span now, because the span starts before the
agent's function is called.

## Conclusion

Moving onto `BedrockAgentCoreApp` removes the code that was only there to
be a server, and with ADOT it removes the tracing code as well. The agent
is one function, and the contract, the health check and the trace context
are the SDK's and ADOT's to look after.

It does not remove the decisions that belong to the agent. Who the caller
is, what a valid request is, how much the process will take on at once and
what a client is told when something fails are all still written here, in
the function and a small piece of middleware.

The agent now stands on what most AgentCore agents stand on, which is
where the next post starts, evaluations as a quality gate.

References:

- https://github.com/levantar-ai/demos/tree/main/agentcore/08-runtime-app
- https://github.com/aws/bedrock-agentcore-sdk-python
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-service-contract.html
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-header-allowlist.html
- https://aws-otel.github.io/docs/getting-started/python-sdk
