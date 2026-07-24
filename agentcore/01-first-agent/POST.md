# What AgentCore actually is, and getting a first agent running on it

## TL;DR;

I deployed a minimal agent container to Amazon Bedrock AgentCore Runtime using
Terraform, invoked it across multiple sessions to see the microVM isolation
and cold starts for myself, and then tore it all down. Along the way I hit
four gotchas which I have written up here, including one where all my
CloudWatch logs silently disappeared. Every number and error message in this
post came from a real deployment on 2026-07-23.

SOURCE CODE - All code for this post is available at:
https://github.com/levantar-ai/demos/tree/main/agentcore/01-first-agent

## Longer version

I have been spending time recently looking at what it takes to run an AI
agent in production on AWS, beyond the point where it works in a notebook.
The agent loop itself is not the hard part. The hard part is everything
around it, in that you need somewhere for it to run for potentially hours at
a time, you need sessions isolated from each other, you need to know who the
agent is acting as when it calls your APIs, and you need somewhere for the
traces to go when it does something you didn't expect.

Amazon Bedrock AgentCore is AWS's answer to that operational shell. It is
worth being clear about what it is not, because the name is misleading in a
couple of ways. It is not a framework, so you keep whatever you are already
using (Strands, LangGraph, CrewAI or your own loop). It is also not tied to
Bedrock models despite the branding, because the runtime just executes a
container you give it and that container can call whatever model it likes.

What you actually get is a set of managed services:

- Runtime - serverless execution of your agent container, one microVM per
  session, sessions up to 8 hours
- Gateway - turns your existing APIs and Lambdas into MCP tools
- Memory - short-term session context and extracted long-term memory
- Identity - inbound auth for callers and outbound OAuth so the agent can
  act on a user's behalf
- Browser and Code Interpreter - managed sandboxed built-in tools
- Observability - OTEL traces and CloudWatch integration on by default

I am planning to work through all of these in this series, one post and one
deployable demo at a time. This post is about getting the smallest thing
that can possibly work onto Runtime.

## The Runtime contract

The contract Runtime has with your container is small. The container must
listen on port 8080, answer `POST /invocations` with your agent logic,
answer `GET /ping` with a health response, and be built for linux/arm64.
That is the whole thing, there is no SDK requirement and no blessed
framework.

To prove that point I wrote the first agent with the Python standard library
only, no dependencies at all, which came out at about 40 lines:

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

It just echoes the prompt back. I kept it deliberately dumb because I wanted
to observe the platform behaviour (cold starts, session isolation, health
checking) without any model calls muddying the timings. Later posts in the
series will make it do something useful.

## 1 - Deploying it with Terraform

Most of the AgentCore tutorials I found use the `agentcore` starter CLI. I
wanted to use Terraform because that is how this would actually ship at
work. The hashicorp/aws provider doesn't cover AgentCore Runtime yet so the
runtime resource comes from the awscc (Cloud Control) provider:

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

Alongside that there is an ECR repository (with immutable tags, so deploys
reference a git SHA rather than latest) and an execution role which the
runtime assumes to pull the image, write logs and call Bedrock models. The
whole stack is five resources.

The build and deploy is then:

```bash
docker buildx build --platform linux/arm64 -t "$REPO:$GIT_SHA" --push agent/
terraform apply -var="image_tag=$GIT_SHA"
```

My first apply failed with the following:

```
Role validation failed for 'arn:aws:iam::<ACCOUNT_ID>:role/demos-agentcore-01-first-agent-runtime'.
Please verify that the role exists and its trust policy allows assumption
by this service (Service: BedrockAgentCoreControl, Status Code: 400)
```

The role did exist, it had been created about three seconds earlier in the
same apply. IAM is eventually consistent and the AgentCore control plane
validated the role before it had propagated. I ran the apply again
immediately and it succeeded, with the runtime creation taking 33 seconds
and the runtime reaching READY about 11 seconds after creation. If you are
scripting this it is worth building in a retry.

NOTE: Runtime names must match `[a-zA-Z][a-zA-Z0-9_]*` which means
underscores only, no hyphens, unlike more or less every other AWS resource.
So you end up with `demos_agentcore_01_first_agent` sitting next to
`demos-agentcore-01-first-agent-runtime` and there is nothing you can do
about it.

## 2 - What the service creates without asking

Describing the deployed runtime with
`aws bedrock-agentcore-control get-agent-runtime` showed a few things I
never configured:

- A workload identity is created automatically for each runtime, which is
  the hook the Identity post later in this series will build on.
- The session lifecycle defaults are visible as actual fields, 900 seconds
  idle timeout and 28,800 seconds (8 hours) maximum lifetime. That is the
  "8 hour agent" headline number in a JSON response.
- Versioning is built in. This deploy was `agentRuntimeVersion: "1"` and
  every image update bumps it automatically.

The full describe output is in the repo at
[artifacts/runtime-describe.json](artifacts/runtime-describe.json).

## 3 - Invoking it and watching the microVMs

Invocation goes through the data plane API. Two things caught me out here.
Session IDs have to be at least 33 characters, and the CLI treats the
payload as base64 unless you tell it otherwise, so my first invocation
failed with `Invalid base64` until I added the binary format flag:

```bash
aws bedrock-agentcore invoke-agent-runtime \
  --cli-binary-format raw-in-base64-out \
  --agent-runtime-arn "$RUNTIME_ARN" \
  --runtime-session-id "$SESSION_ID" \
  --payload '{"prompt": "hello"}' response.json
```

Here are four real invocations across two sessions. The wall-clock times
include roughly 0.8 seconds of local aws-vault and CLI overhead:

| # | Session | Time | Observation |
|---|---------|------|-------------|
| 1 | A (new) | 6.89s | cold start, microVM spin up plus container boot |
| 2 | A (warm) | 1.35s | the session's microVM is alive and waiting |
| 3 | B (new) | 4.53s | a new session pays its own cold start |
| 4 | B (warm) | 1.27s | roughly 0.5s server-side once warm |

The third row is the interesting one. Runtime's isolation model is one
microVM per session, so session B could not reuse session A's warm
environment even though the same runtime, same container and same version
was already running. The CloudWatch logs backed this up, in that my two
sessions produced exactly two `[runtime-logs]` streams in the runtime's log
group.

## 4 - The silent log eater

My first deployment produced completely empty log streams and I spent a
while assuming I had the IAM permissions wrong. Nothing was wrong with
AgentCore at all. The agent logs with `print()` and Python block-buffers
stdout when it is not attached to a TTY, so the output was sitting in a
buffer and never being flushed. One line in the Dockerfile fixes it:

```dockerfile
ENV PYTHONUNBUFFERED=1
```

Shipping the fix turned out to be a nice little demonstration of the update
flow. Because the ECR tags are immutable I pushed the fixed image as a new
tag, ran one terraform apply which updated the runtime in place in 12
seconds, and `agentRuntimeVersion` bumped to 2 automatically. After that the
logs landed immediately:

```
agent listening on :8080
127.0.0.1 "POST /invocations HTTP/1.1" 200 -
127.0.0.1 "GET /ping HTTP/1.1" 200 -
127.0.0.1 "GET /ping HTTP/1.1" 200 -
...
```

Something I only learned from seeing the logs is that the platform polls
`GET /ping` continuously between invocations, so the health endpoint is
doing real work and is worth implementing properly rather than as an
afterthought. The log group also contained `otel-rt-logs` and `spans`
streams, which is OTEL plumbing that exists before you have configured any
observability at all. I want to pull on that thread in a later post.

## Teardown

```bash
terraform destroy
```

All five resources destroyed in about 20 seconds (the ECR repository has
`force_delete` set so the pushed images go with it). Runtime bills by
consumed CPU and memory seconds, so the whole exercise of two deploys, six
invocations and an hour of mostly idle runtime cost pennies.

## Conclusion

This experiment has taught me that the Runtime part of AgentCore is
genuinely small to get started with, in that a 40 line stdlib Python server
and five Terraform resources gets you a deployed agent with per-session
microVM isolation that you can see for yourself in the timings and the log
streams. It also handed me four gotchas (IAM propagation on first apply,
underscore-only runtime names, the base64 payload flag, and Python stdout
buffering) which are all cheap to avoid once you know about them and
annoying when you don't.

What I don't have yet is a trustworthy path to production, because this
deploy ran from my laptop with admin credentials. The next post covers
wiring this into CI properly with GitHub OIDC so there are no stored AWS
keys, namespaced Terraform state, and a pipeline where every demo in the
repo gets tests, quality gates and security scanning on every change.

References:

- https://github.com/levantar-ai/demos/tree/main/agentcore/01-first-agent
- https://docs.aws.amazon.com/bedrock-agentcore/
- https://registry.terraform.io/providers/hashicorp/awscc/latest/docs/resources/bedrockagentcore_runtime
