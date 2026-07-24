# Deployment artifacts — captured from a real run

Everything below was captured from an actual deploy → invoke → destroy cycle
of this demo on 2026-07-23 (region `us-east-1`, account ID redacted). Use
freely in the blog post.

## What was deployed

Five resources via `terraform apply` (state key
`terraform/demos/agentcore/01-first-agent/terraform.tfstate`):

| Resource | Name |
|----------|------|
| ECR repository (immutable tags) | `demos/agentcore/01-first-agent` |
| ECR lifecycle policy | keep last 10 images |
| IAM execution role | `demos-agentcore-01-first-agent-runtime` |
| IAM role policy | ECR pull, logs, X-Ray, Bedrock invoke, workload token |
| AgentCore Runtime | `demos_agentcore_01_first_agent` |

The container is the ~40-line stdlib Python server in [`../agent/main.py`](../agent/main.py)
implementing the Runtime HTTP contract (`POST /invocations`, `GET /ping`),
built for `linux/arm64` and tagged with the git SHA
(`f3f7d032577805764aeca5db6caf59915f7250a9`).

## Gotchas hit during deploy (blog gold)

1. **IAM propagation race.** The first apply failed with
   `Role validation failed ... verify that the role exists and its trust
   policy allows assumption by this service (Service: BedrockAgentCoreControl,
   Status Code: 400)` because the execution role had been created ~3 seconds
   earlier. An immediate retry succeeded — runtime creation then took 33s.
2. **CLI payloads are base64 by default.** `aws bedrock-agentcore
   invoke-agent-runtime --payload '{"prompt": ...}'` fails with
   `Invalid base64` unless you pass `--cli-binary-format raw-in-base64-out`.
3. **Runtime names are underscore-only** (`[a-zA-Z][a-zA-Z0-9_]*`), unlike
   most AWS resources — hence `demos_agentcore_01_first_agent` while every
   sibling resource uses hyphens.
4. **Python stdout buffering ate the logs.** The first deploy produced empty
   CloudWatch log streams: the agent logs with `print()`, and Python
   block-buffers stdout in containers, so nothing was ever flushed. Fix is
   `ENV PYTHONUNBUFFERED=1` in the Dockerfile. Updating the runtime to the
   fixed image was a single in-place `terraform apply` (12s,
   `agentRuntimeVersion` bumps automatically) — immutable ECR tags meant the
   fix shipped as a new tag, exactly as designed.

## What the service creates for you

From [`runtime-describe.json`](runtime-describe.json) (control-plane
`get-agent-runtime` output):

- A **workload identity** is auto-created per runtime:
  `workload-identity-directory/default/workload-identity/demos_agentcore_01_first_agent-<id>`
- **Lifecycle defaults:** 900s idle session timeout, 28,800s (8h) max session
  lifetime — the numbers behind the "8-hour execution window" headline.
- Versioning is built in: this deploy is `agentRuntimeVersion: "1"`.
- Status went `CREATING → READY` in ~11s (createdAt vs lastUpdatedAt).

## Invocation transcript and timings

Four invocations across two sessions (`--runtime-session-id` must be ≥33
chars). Wall-clock includes ~0.8s of local `aws-vault` + CLI overhead:

| # | Session | Wall-clock | Response |
|---|---------|-----------|----------|
| 1 | A (new) | **6.89s** | `{"result": "echo: hello from invocation 1"}` |
| 2 | A (warm) | **1.35s** | `{"result": "echo: hello from invocation 2"}` |
| 3 | B (new) | **4.53s** | `{"result": "echo: hello from invocation 3"}` |
| 4 | B (warm) | **1.27s** | `{"result": "echo: hello from invocation 4"}` |

The story in the numbers: **each new session pays its own cold start**
(microVM spin-up: ~6.9s first ever, ~4.5s for the second session), then
warm invocations settle around 1.3s wall-clock (~0.5s server-side). Session
isolation is real, not a metaphor — see the log streams below.

Response metadata per invocation:

```json
{
  "runtimeSessionId": "blog-demo-session-aaaaaaaaaaaaaaaaaaaaaaaaaaaa-001",
  "contentType": "application/json",
  "statusCode": 200
}
```

## Observability out of the box

With zero OTEL configuration in the agent code, the service created log group
`/aws/bedrock-agentcore/runtimes/demos_agentcore_01_first_agent-<id>-DEFAULT`
containing:

```
2026/07/23/[runtime-logs]56cebe54-...   ← one stream per session microVM
2026/07/23/[runtime-logs]d5742c5f-...   ← (two sessions → two streams)
otel-rt-logs                            ← OTEL runtime logs
spans                                   ← OTEL trace spans
```

Two invocation sessions produced exactly two `[runtime-logs]` streams —
visible proof of per-session isolation, and a ready-made segue into the
observability post (07).

Once `PYTHONUNBUFFERED=1` was in place, the container's stdout landed
straight in CloudWatch (see
[`runtime-logs-excerpt.txt`](runtime-logs-excerpt.txt)) — including the
discovery that the platform **continuously polls `GET /ping`** between
invocations: the health endpoint is load-bearing, not ceremonial. Timings
were reproducible after the image update too: fresh session 4.37s, warm 1.33s.

## Teardown

`terraform destroy` removes all five resources (ECR `force_delete` clears
the pushed images). Total cost of the whole exercise: pennies.
