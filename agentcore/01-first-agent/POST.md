# What AgentCore actually is — and your first agent running on it

*Post 1 of a series on Amazon Bedrock AgentCore. Every post in this series
ships with a working demo you can deploy yourself; this one lives in
[`agentcore/01-first-agent/`](.), and every number and error message below
came from a real deployment on 2026-07-23.*

---

If you've tried to put an AI agent into production on AWS, you've probably
discovered the gap between "works in a notebook" and "runs for real users".
The agent loop itself is the easy part — a model, some tools, a while loop.
What's hard is everything around it: where does it run for up to eight hours?
How do sessions stay isolated from each other? Who is the agent acting as
when it calls your APIs? Where do the traces go when it does something weird?

Amazon Bedrock AgentCore is AWS's answer to that gap. It is **not** a
framework — you keep Strands, LangGraph, CrewAI, or your own hand-rolled
loop. It is **not** tied to Bedrock models either, despite the name; the
runtime executes an arbitrary container that can call any model. What it
actually is: a set of managed services for the operational shell around an
agent:

- **Runtime** — serverless execution of your agent container, one microVM
  per session, up to 8-hour sessions
- **Gateway** — turns your APIs and Lambdas into MCP tools
- **Memory** — short-term session context and extracted long-term memory
- **Identity** — inbound auth for callers, outbound OAuth for the agent
  acting on a user's behalf
- **Browser** and **Code Interpreter** — managed, sandboxed built-in tools
- **Observability** — OTEL traces and CloudWatch integration, on by default

This series works through all of them, one post and one deployable demo at a
time. Today: the smallest thing that can possibly work on Runtime.

## The Runtime contract

Runtime's contract with your container is refreshingly small. It must:

1. listen on port **8080**,
2. answer `POST /invocations` with your agent logic,
3. answer `GET /ping` with a health response,
4. be built for **linux/arm64**.

That's it. No SDK required, no framework blessed. To prove the point, our
first agent is ~40 lines of standard-library Python — no dependencies at all:

```python
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/ping":
            self._send(200, {"status": "healthy"})

    def do_POST(self):
        if self.path == "/invocations":
            payload = json.loads(self.rfile.read(length) or b"{}")
            self._send(200, {"result": f"echo: {payload.get('prompt', '')}"})
```

It just echoes. That's deliberate: this post is about the *platform*, and an
echo agent makes the platform's behaviour — cold starts, session isolation,
health checking — impossible to miss. Post 3 onwards makes it intelligent.

## Deploying it with Terraform

Most AgentCore tutorials use the `agentcore` starter CLI. We're using
Terraform, because that's how this will actually ship at work. The
`hashicorp/aws` provider doesn't cover AgentCore Runtime yet, so the runtime
resource comes from the `awscc` (Cloud Control) provider:

```hcl
resource "awscc_bedrockagentcore_runtime" "agent" {
  agent_runtime_name = "demos_agentcore_01_first_agent"
  role_arn           = aws_iam_role.runtime.arn

  agent_runtime_artifact = {
    container_configuration = {
      container_uri = "${aws_ecr_repository.agent.repository_url}:${var.image_tag}"
    }
  }

  network_configuration  = { network_mode = "PUBLIC" }
  protocol_configuration = "HTTP"
}
```

Alongside it: an ECR repository (immutable tags — deploys reference a git
SHA, never `latest`) and an execution role the runtime assumes to pull the
image, write logs, and call Bedrock models. The full stack is five resources.

Build, push, apply:

```bash
docker buildx build --platform linux/arm64 -t "$REPO:$GIT_SHA" --push agent/
terraform apply -var="image_tag=$GIT_SHA"
```

### Gotcha #1: the IAM propagation race

The first apply failed:

```
Role validation failed for 'arn:aws:iam::<ACCOUNT_ID>:role/demos-agentcore-01-first-agent-runtime'.
Please verify that the role exists and its trust policy allows assumption
by this service (Service: BedrockAgentCoreControl, Status Code: 400)
```

The role *did* exist — for about three seconds. IAM is eventually
consistent, and AgentCore's control plane validated the role before it had
propagated. An immediate retry succeeded; runtime creation took 33 seconds
and the runtime reached `READY` roughly 11 seconds after creation. If you're
scripting this, build in a retry.

### Gotcha #2: runtime names are underscore-only

Runtime names must match `[a-zA-Z][a-zA-Z0-9_]*` — no hyphens, unlike
practically every other AWS resource. Hence the slightly jarring
`demos_agentcore_01_first_agent` sitting next to
`demos-agentcore-01-first-agent-runtime`.

## What you get without asking

Describing the deployed runtime (`aws bedrock-agentcore-control
get-agent-runtime`) reveals several things you never configured:

- **A workload identity**, auto-created per runtime — the hook that post 6
  (Identity) builds on.
- **Session lifecycle defaults:** 900s idle timeout, 28,800s (8 hours)
  maximum lifetime. That's the "8-hour agent" headline, as an actual field.
- **Versioning:** the deploy is `agentRuntimeVersion: "1"`, and every image
  update bumps it automatically.

## Invoking it — and watching the microVMs

Invocation goes through the data-plane API. Session IDs must be at least 33
characters, and — **gotcha #3** — the CLI treats `--payload` as base64
unless you say otherwise:

```bash
aws bedrock-agentcore invoke-agent-runtime \
  --cli-binary-format raw-in-base64-out \
  --agent-runtime-arn "$RUNTIME_ARN" \
  --runtime-session-id "$SESSION_ID" \
  --payload '{"prompt": "hello"}' response.json
```

Here are four real invocations across two sessions (wall-clock, including
~0.8s of local CLI overhead):

| # | Session | Time | What it tells you |
|---|---------|------|-------------------|
| 1 | A (new) | **6.89s** | cold start: microVM spin-up + container boot |
| 2 | A (warm) | **1.35s** | the session's microVM is alive and waiting |
| 3 | B (new) | **4.53s** | a *new session pays its own cold start* |
| 4 | B (warm) | **1.27s** | ~0.5s server-side once warm |

That third row is the important one. Runtime's isolation model is one
microVM per session — so session B couldn't reuse session A's warm
environment even though the same runtime, same container, same version was
already running. Isolation is a genuine boundary, not a scheduling
preference. CloudWatch corroborates: two sessions produced exactly two
`[runtime-logs]` streams in the runtime's log group.

## Gotcha #4: the silent log-eater

The first deployment produced completely empty log streams. Nothing was
wrong with AgentCore — Python block-buffers stdout when it isn't a TTY, so
the agent's `print()` output never flushed before sitting in a buffer
forever. One Dockerfile line fixes it:

```dockerfile
ENV PYTHONUNBUFFERED=1
```

Shipping the fix was its own mini-demo of the update flow: build a new
image tag (immutable tags, remember), one `terraform apply`, 12 seconds of
in-place update, `agentRuntimeVersion` bumped to 2. After that, logs landed
immediately — and revealed that the platform **continuously polls
`GET /ping`** between invocations. The health endpoint is load-bearing, not
ceremonial: implement it properly.

```
agent listening on :8080
127.0.0.1 "POST /invocations HTTP/1.1" 200 -
127.0.0.1 "GET /ping HTTP/1.1" 200 -
127.0.0.1 "GET /ping HTTP/1.1" 200 -
...
```

The log group also contains `otel-rt-logs` and `spans` streams — OTEL
plumbing that exists before you've configured any observability at all.
Post 7 pulls on that thread.

## Tear-down and the bill

```bash
terraform destroy   # 5 resources destroyed, ~20 seconds
```

Runtime bills by consumed CPU/memory seconds, so an experiment like this —
two deploys, six invocations, an hour of mostly-idle runtime — costs
pennies. Post 10 does the real cost modelling at production volumes.

## Where this leaves us

We have a container contract you can satisfy in 40 lines of stdlib Python, a
five-resource Terraform stack, evidence that per-session microVM isolation
is real, and four gotchas you now get to skip. What we don't have is a
*trustworthy path to production* — this deploy ran from a laptop with admin
credentials.

Next post: wiring this into CI properly — GitHub OIDC (no stored AWS keys),
namespaced Terraform state, and a pipeline where every demo in this repo
gets tests, quality gates, and security scanning on every change.

---

*All code, Terraform, and captured artifacts for this post:
[`agentcore/01-first-agent/`](.) — including the
[raw deployment evidence](artifacts/README.md) if you want to check my
numbers.*
