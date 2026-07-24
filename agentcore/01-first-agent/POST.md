# What AgentCore actually is, and getting a first agent running on it

## TL;DR;

How to deploy an agent container to Amazon Bedrock AgentCore Runtime with
Terraform, what the platform gives you that you didn't ask for, and the
handful of things that will catch you out on your first deployment,
including one that makes your CloudWatch logs silently disappear.

SOURCE CODE - All code for this post is available at:
https://github.com/levantar-ai/demos/tree/main/agentcore/01-first-agent

## Longer version

The gap between an agent that works in a notebook and an agent running in
production is not the agent loop, it is everything around it. You need
somewhere for it to run for potentially hours at a time, you need sessions
isolated from each other, you need to know who the agent is acting as when
it calls your APIs, and you need somewhere for the traces to go when it does
something you didn't expect.

Amazon Bedrock AgentCore is AWS's answer to that operational shell, and it
is worth being clear about what it is not, because the name misleads in two
ways. It is not a framework, so you keep whatever you are already using
(Strands, LangGraph, CrewAI or your own loop). It is also not tied to
Bedrock models, because the runtime executes a container you give it and
that container can call whatever model it likes.

What you actually get is a set of managed services:

- Runtime - serverless execution of your agent container, one microVM per
  session, sessions up to 8 hours
- Gateway - turns your existing APIs and Lambdas into MCP tools
- Memory - short-term session context and extracted long-term memory
- Identity - inbound auth for callers and outbound OAuth so the agent can
  act on a user's behalf
- Browser and Code Interpreter - managed sandboxed built-in tools
- Observability - OTEL traces and CloudWatch integration on by default

This series works through all of them, one post and one deployable demo at a
time. This post covers Runtime, using the smallest agent that can possibly
work so the platform behaviour is easy to see.

## The Runtime contract

The contract Runtime has with your container is small. The container must
listen on port 8080, answer `POST /invocations` with your agent logic,
answer `GET /ping` with a health response, and be built for linux/arm64.
That is the whole thing, there is no SDK requirement and no blessed
framework.

The demo agent is the Python standard library only, no dependencies, about
40 lines:

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

It just echoes the prompt back. Keeping the agent dumb at this stage is a
deliberate choice, because it lets you observe the platform (cold starts,
session isolation, health checking) without model calls muddying the
timings. Later posts in the series make it do something useful.

## 1 - Deploying it with Terraform

Most AgentCore tutorials use the `agentcore` starter CLI, which is fine for
a first look but not how you will ship at work. The hashicorp/aws provider
has native AgentCore support from v6, with a whole family of
`aws_bedrockagentcore_*` resources covering runtimes, gateways, memory,
browser, code interpreter, workload identity and credential providers, so
there is no need to reach for the awscc provider or CloudFormation. The
runtime is:

```hcl
resource "aws_bedrockagentcore_agent_runtime" "agent" {
  agent_runtime_name = "demos_agentcore_01_first_agent"
  role_arn           = aws_iam_role.runtime.arn

  agent_runtime_artifact {
    container_configuration {
      container_uri = "${aws_ecr_repository.agent.repository_url}:${var.image_tag}"
    }
  }

  network_configuration {
    network_mode = "PUBLIC"
  }

  protocol_configuration {
    server_protocol = "HTTP"
  }
}
```

Alongside that you want an ECR repository with immutable tags, so deploys
reference a git SHA rather than latest, and an execution role which the
runtime assumes to pull the image, write logs and call Bedrock models. The
whole stack is five resources.

The build and deploy is then:

```bash
docker buildx build --platform linux/arm64 -t "$REPO:$GIT_SHA" --push agent/
terraform apply -var="image_tag=$GIT_SHA"
```

One thing to be aware of when the execution role and the runtime are created
in the same apply is IAM eventual consistency. The AgentCore control plane
validates the role at creation time and can reject it before it has
propagated, which looks like this:

```
Role validation failed for 'arn:aws:iam::<ACCOUNT_ID>:role/demos-agentcore-01-first-agent-runtime'.
Please verify that the role exists and its trust policy allows assumption
by this service (Service: BedrockAgentCoreControl, Status Code: 400)
```

The role does exist, it was created seconds earlier in the same apply. The
aws provider handles this internally and creates the runtime first time, but
if you are driving the API directly, or using the awscc provider which
surfaces this error on a fresh stack, build a retry into your pipeline. The
runtime reaches READY around 10 seconds after creation.

NOTE: Runtime names must match `[a-zA-Z][a-zA-Z0-9_]*` which means
underscores only, no hyphens, unlike more or less every other AWS resource.
So you end up with `demos_agentcore_01_first_agent` sitting next to
`demos-agentcore-01-first-agent-runtime` and there is nothing you can do
about it.

## 2 - What the service creates without asking

Describing the deployed runtime with
`aws bedrock-agentcore-control get-agent-runtime` shows a few things you
never configured and should know about:

- A workload identity is created automatically for each runtime. This is
  the foundation the Identity services build on, and a later post in this
  series covers it properly.
- The session lifecycle defaults are visible as actual fields, 900 seconds
  idle timeout and 28,800 seconds (8 hours) maximum lifetime. That is the
  "8 hour agent" headline number in a JSON response.
- Versioning is built in. A fresh deploy is `agentRuntimeVersion: "1"` and
  every image update bumps it automatically, which matters later for
  rollbacks.

The full describe output is in the repo at
[artifacts/runtime-describe.json](artifacts/runtime-describe.json).

## 3 - Invoking it and seeing the microVM isolation

Invocation goes through the data plane API and there are two things to know
before your first call. Session IDs must be at least 33 characters, and the
CLI treats the payload as base64 unless you pass the binary format flag, so
without it you get `Invalid base64` back:

```bash
aws bedrock-agentcore invoke-agent-runtime \
  --cli-binary-format raw-in-base64-out \
  --agent-runtime-arn "$RUNTIME_ARN" \
  --runtime-session-id "$SESSION_ID" \
  --payload '{"prompt": "hello"}' response.json
```

Here are four invocations across two sessions. The wall-clock times include
roughly 0.8 seconds of local aws-vault and CLI overhead:

| # | Session | Time | Observation |
|---|---------|------|-------------|
| 1 | A (new) | 6.89s | cold start, microVM spin up plus container boot |
| 2 | A (warm) | 1.35s | the session's microVM is alive and waiting |
| 3 | B (new) | 4.53s | a new session pays its own cold start |
| 4 | B (warm) | 1.27s | roughly 0.5s server-side once warm |

The third row is the one to understand. Runtime's isolation model is one
microVM per session, so a new session cannot reuse another session's warm
environment even when the same runtime, same container and same version is
already running. Every new session pays a cold start, which is a real
consideration if your workload creates many short sessions. The CloudWatch
logs back this up, in that two sessions produce exactly two
`[runtime-logs]` streams in the runtime's log group.

## 4 - The silent log eater

If your log streams are empty after your first deployment, before you go
digging through IAM policies, check your container's stdout buffering. A
Python agent that logs with `print()` will block-buffer stdout when it is
not attached to a TTY, so the output sits in a buffer and never reaches
CloudWatch. One line in the Dockerfile fixes it:

```dockerfile
ENV PYTHONUNBUFFERED=1
```

Shipping a fix like this also demonstrates the update flow. With immutable
ECR tags the fixed image goes out as a new tag, one terraform apply updates
the runtime in place in about 12 seconds, and `agentRuntimeVersion` bumps
automatically. With the buffering fixed the logs land immediately:

```
agent listening on :8080
127.0.0.1 "POST /invocations HTTP/1.1" 200 -
127.0.0.1 "GET /ping HTTP/1.1" 200 -
127.0.0.1 "GET /ping HTTP/1.1" 200 -
...
```

Note the `GET /ping` lines. The platform polls your health endpoint
continuously between invocations, so implement it properly rather than as an
afterthought, because it is doing real work. The log group also contains
`otel-rt-logs` and `spans` streams, which is OTEL plumbing that exists
before you have configured any observability at all. The observability post
in this series pulls on that thread.

## Teardown

```bash
terraform destroy
```

All five resources destroy in about 20 seconds (set `force_delete` on the
ECR repository so the pushed images go with it). Runtime bills by consumed
CPU and memory seconds, so an exercise like this, a couple of deploys and a
handful of invocations, costs pennies. The cost post later in the series
covers what the pricing model looks like at production volumes, where the
session lifecycle defaults above start to matter.

## Conclusion

Runtime is a small surface to get started with. A 40 line stdlib Python
server and five Terraform resources gets you a deployed agent with
per-session microVM isolation that you can verify yourself in the timings
and the log streams. The things that catch people out on a first deployment,
IAM propagation on the first apply, the underscore-only runtime names, the
base64 payload flag and stdout buffering, are all cheap to avoid once you
know about them.

What this post does not give you is a trustworthy path to production,
because this deploy ran from a laptop with admin credentials. The next post
covers wiring this into CI properly with GitHub OIDC so there are no stored
AWS keys, namespaced Terraform state, and a pipeline where every demo in the
repo gets tests, quality gates and security scanning on every change.

References:

- https://github.com/levantar-ai/demos/tree/main/agentcore/01-first-agent
- https://docs.aws.amazon.com/bedrock-agentcore/
- https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_agent_runtime
