# Letting an agent run code, without letting it run loose

## TL;DR;

How to give an agent a real Python sandbox with AgentCore Code
Interpreter, so it can analyse data it was handed rather than guess at
it, and what the sandbox does and does not have access to.

> SOURCE CODE - All code for this post is available at:
> https://github.com/levantar-ai/demos/tree/main/agentcore/04-builtin-tools

## Longer version

Ask a language model to compute statistics over a few hundred rows and it
will produce numbers that look right. Give it somewhere to actually run
pandas and it produces numbers you can check, from code you can read, over
data you can point at. That is the whole argument for code execution as a
tool.

The problem is where that execution happens. Parsing a stranger's CSV
with pandas inside your agent's own process puts a parser you did not
write, working on data you do not control, right next to your
credentials. Go a step further and execute model-generated code there and
the exposure is worse again.

AgentCore Code Interpreter is a managed sandbox for exactly this. Your
agent writes files into a session, runs code there, and reads results
back as text. This demo keeps the code fixed and author-written, so what
is being isolated is the *processing of untrusted data*, which is the
common case; the same mechanism is what you would use for
model-generated code, with more input and output controls on top. This
post wires one up and then pokes at the walls.

![Architecture](architecture.png)

## 1 - The sandbox

One resource, and the network mode is the control this post turns on:

```hcl
resource "aws_bedrockagentcore_code_interpreter" "sandbox" {
  name        = "demos_agentcore_04_interpreter"
  description = "Sandboxed pandas analysis for the demos series"

  network_configuration {
    network_mode = "SANDBOX"
  }
}
```

`SANDBOX` means the session gets no outbound internet access. The other
option is `PUBLIC`, which gives the sandbox outbound internet access, and
you want
to be deliberate about choosing it, because that is the mode where code
running in the session could reach the network on its own. The threat is
the code that executes, whether you wrote it or a model did, not the CSV
sitting on disk.

> NOTE: `SANDBOX` is the egress control, not the whole boundary. IAM
> decides who can start and invoke a session, you decide what data goes
> into one, and your agent decides what comes back out to the caller.
> Isolating the network does not make everything in the session safe to
> return.

The runtime role gets the three actions the agent actually calls, scoped
to this one sandbox:

```hcl
{
  Sid    = "CodeInterpreter"
  Effect = "Allow"
  Action = [
    "bedrock-agentcore:StartCodeInterpreterSession",
    "bedrock-agentcore:InvokeCodeInterpreter",
    "bedrock-agentcore:StopCodeInterpreterSession"
  ]
  Resource = aws_bedrockagentcore_code_interpreter.sandbox.code_interpreter_arn
}
```

## 2 - The agent

The agent's job is to move data in, run code, and read results out. It
never parses the CSV itself:

```python
def _call(session_id, name, **arguments):
    response = client().invoke_code_interpreter(
        codeInterpreterIdentifier=os.environ["CODE_INTERPRETER_ID"],
        sessionId=session_id,
        name=name,
        arguments=arguments,
    )
    return _consume(response)


def write_files(session_id, path, text):
    return _call(session_id, "writeFiles", content=[{"path": path, "text": text}])


def execute_code(session_id, code, language="python"):
    return _call(session_id, "executeCode", code=code, language=language)


def analyse(csv_text, session_id):
    write_files(session_id, "data.csv", csv_text)
    return execute_code(session_id, ANALYSIS)
```

The service exposes one data-plane call, `invoke_code_interpreter`, which
takes a tool name and an arguments blob rather than a method per tool. That
is the shape of an MCP `tools/call`, the same protocol the Gateway spoke in
post 02, and it exists so an agent can forward a model's tool choice
straight through without a dispatch table. The useful names are
`writeFiles`, `executeCode`, `executeCommand`, `readFiles` and `listFiles`.

This agent's code is fixed, so it gains nothing from the dynamic shape and
wraps the two tools it uses as functions with named parameters. That also
puts the stream handling in one place. Responses arrive as an event stream,
and a tool that fails sets `isError` inside that stream rather than raising,
so `_consume` drains every call and raises on `isError`. Skip that and a
failed run looks exactly like a successful empty one.

Sessions are the thing to be careful with, because one lives until its
timeout whether or not you are still using it. The agent opens a session,
works in it, and stops it in a `finally` so a failed run cleans up too:

```python
def session_for(interpreter, name):
    resp = client().start_code_interpreter_session(
        codeInterpreterIdentifier=interpreter,
        name=name,
        sessionTimeoutSeconds=900,
    )
    return resp["sessionId"]


session_id = None
try:
    session_id = self.start(interpreter, "analysis")
    self._send(200, {"result": self.run(csv_text, session_id)})
finally:
    if session_id is not None:
        self.stop(interpreter, session_id)
```

> NOTE: files land in the session's working directory, not in `/tmp`. Write
> to `data.csv` and read `data.csv`, and resist the urge to be clever with
> absolute paths.

<!-- -->

> NOTE: sessions outlive the call that created them, up to
> `sessionTimeoutSeconds`, and a sandbox with live sessions refuses to
> delete (`ConflictException: ... cannot be deleted. There are 2 active
> sessions`), so stop sessions rather than waiting them out.

## 3 - Analysing something

Post a CSV to the agent and the numbers come back computed rather than
imagined:

```bash
cat payload.json
# {"csv": "order_id,items,total\n1001,3,42.50\n1002,1,12.00\n1003,7,131.75\n1004,2,28.40\n1005,5,88.20\n"}

aws bedrock-agentcore invoke-agent-runtime \
  --cli-binary-format raw-in-base64-out \
  --agent-runtime-arn "$ARN" \
  --runtime-session-id analysis-session-000000000000000001 \
  --payload file://payload.json \
  --region us-east-1 /dev/stdout
```

```
order_id     items       total
count     5.000000  5.000000    5.000000
mean   1003.000000  3.600000   60.570000
std       1.581139  2.408319   48.863299
min    1001.000000  1.000000   12.000000
25%    1002.000000  2.000000   28.400000
50%    1003.000000  3.000000   42.500000
75%    1004.000000  5.000000   88.200000
max    1005.000000  7.000000  131.750000

rows: 5
```

Pandas was already present in the sandbox image at the time of writing, so
there was no dependency management to do for straightforward analysis. That
is an observation about the managed image rather than a documented contract,
so check what you actually need is there before you depend on it.

## 4 - Testing the walls

The interesting part is what happens when code in the sandbox tries to
reach out. Running this inside a `SANDBOX` session:

```python
import urllib.request
urllib.request.urlopen("https://example.com", timeout=8)
```

```
blocked: URLError <urlopen error [Errno -2] Name or service not known>
```

The lookup failed at name resolution rather than at connect time. Next, a
look for credentials in the environment and a probe of the instance
metadata address:

```python
keys = [k for k in os.environ if "AWS" in k or "TOKEN" in k]
urllib.request.urlopen("http://169.254.169.254/latest/meta-data/", timeout=5)
```

```
aws-ish env vars: []
metadata request denied: HTTP 401
```

Read that 401 carefully, because it is weaker evidence than it looks. A 401
is an answer rather than a refusal to answer, and IMDSv2 returns exactly
that to an unauthenticated GET because no token has been fetched first. The
environment scan is narrow in the same way, since credentials need not sit
in a variable whose name contains `AWS`. Treat both as corroboration rather
than proof.

The guarantee to design against is the documented `SANDBOX` behaviour, which
is that the session has no outbound internet egress. What you get is code
running on untrusted data with no outbound route to the internet. What the
session hands back still travels through your agent, so what reaches the
caller stays your decision.

## Conclusion

A managed sandbox turns "the model says the mean is about sixty" into a
computed answer, and it moves the processing of untrusted data off your
agent's microVM into a session with no outbound internet egress. One Terraform
resource, three IAM actions and a couple of API calls, with `SANDBOX` as
the egress control and IAM, session lifecycle and what you return to the
caller making up the rest of the boundary.

The next post gives the agent an identity of its own, inbound
authentication for callers and outbound OAuth so it can act on a user's
behalf.

References:

- https://github.com/levantar-ai/demos/tree/main/agentcore/04-builtin-tools
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-security-best-practices.html
- https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_code_interpreter
