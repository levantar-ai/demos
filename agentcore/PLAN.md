# AgentCore blog series — plan and progress

Ten posts on Amazon Bedrock AgentCore, each with a working demo in this
repo. Every demo is standalone; later demos copy the previous one forward and
the post shows the diff. Tick items as they complete.

## Repo foundations

- [x] `agentcore/` category structure (one standalone dir per post)
- [x] CI pipeline (verification only): per-demo tests + quality + security
  (terraform validate, tflint, Trivy, ruff, pytest/go test, arm64 build check)
- [x] CI has no AWS access at all — all deploys/teardowns are run locally
  via the Makefile (the earlier OIDC deploy role was destroyed and removed)
- [x] First local deploy of demo 01: deployed, invoked (6 invocations across
  3 sessions), artifacts captured, torn down (2026-07-23)

## Posts

### 01 — What AgentCore is, and your first agent running on it
Positioning intro (vs. Bedrock Agents, Lambda loops, self-hosted frameworks;
the seven services), then deploy a minimal agent to Runtime: container
contract, microVM session isolation, invocation.
- [x] Demo scaffolded (`01-first-agent/`)
- [x] Demo deployed and invoked; blog artifacts in `01-first-agent/artifacts/`
  (timings, gotchas, logs, runtime description); resources destroyed after
- [x] Post drafted (`01-first-agent/POST.md`)
- [ ] Post published

### 02 — Giving your agent tools with AgentCore Gateway
APIs and Lambdas as MCP tools via Gateway targets; semantic tool search.
Demo: the agent answers questions it couldn't before, via a Gateway target.
- [ ] Demo built (`02-gateway/`)
- [ ] Demo deployed and invocable
- [ ] Post drafted
- [ ] Post published

### 03 — Short-term and long-term memory
Session context vs. extracted long-term memory, strategies, namespaces.
Demo: agent recalls user preferences across separate sessions.
- [ ] Demo built (`03-memory/`)
- [ ] Demo deployed and invocable
- [ ] Post drafted
- [ ] Post published

### 04 — Code Interpreter and Browser built-in tools
Sandboxed execution and cloud browser; the security model of agent-run code.
Demo: agent analyses an uploaded CSV and completes a live web task.
- [ ] Demo built (`04-builtin-tools/`)
- [ ] Demo deployed and invocable
- [ ] Post drafted
- [ ] Post published

### 05 — Identity: who is your agent acting as?
Inbound auth (Cognito/OIDC) and outbound OAuth token vaulting.
Demo: agent accesses a user's GitHub/Google account on their behalf, with
consent flow.
- [ ] Demo built (`05-identity/`)
- [ ] Demo deployed and invocable
- [ ] Post drafted
- [ ] Post published

### 06 — Observability: tracing an agent's reasoning
OTEL traces through Runtime/Gateway/Memory in CloudWatch; session debugging.
Demo: debug a deliberately-broken agent run via its trace.
- [ ] Demo built (`06-observability/`)
- [ ] Demo deployed and invocable
- [ ] Post drafted
- [ ] Post published

### 07 — Evals: testing agent behaviour as a quality gate
Tool contract tests, mocked-model units, LLM-as-judge evals as a gate.
Demo: a PR fails CI because an eval regressed, then passes after a fix.
- [ ] Demo built (`07-evals/`)
- [ ] Demo deployed and invocable
- [ ] Post drafted
- [ ] Post published

### 08 — Multi-agent patterns on AgentCore
Supervisor/worker, agents calling agents, A2A vs. MCP, and when multi-agent
is warranted. Demo: split the series agent into a supervisor plus two
specialists.
- [ ] Demo built (`08-multi-agent/`)
- [ ] Demo deployed and invocable
- [ ] Post drafted
- [ ] Post published

### 09 — Cost, quotas, and the bill nobody modelled
Consumption pricing; session duration and memory strategy as cost drivers.
Demo: cost dashboard/script pulling real spend from the series agents and
projecting at 10k sessions/month.
- [ ] Demo built (`09-cost/`)
- [ ] Demo deployed and invocable
- [ ] Post drafted
- [ ] Post published

### 10 — Case study: from prototype to production
Retrospective: the finished architecture, what AgentCore saved, where it
fought back, and a decision framework. Demo: end-to-end walkthrough of the
finished system.
- [ ] Demo built (`10-case-study/`)
- [ ] Demo deployed and invocable
- [ ] Post drafted
- [ ] Post published

## Series format

- Happy path only, no edge-case deep-dives; blocking necessities get a
  one-line NOTE at the point of use. Keep posts short.
- Every post has at least one architecture diagram generated with the
  Python `diagrams` library (`diagram.py` + committed PNG per demo).
- Voice per `~/.claude/andy-rea-voice.md` (experienced practitioner, not
  learner diary).

## Notes

- Differentiator posts (least covered elsewhere): 05, 07, 09.
- AgentCore moves fast — pin SDK/provider versions in each demo and state the
  version in each post.
- Trimmed five-post version if needed: 01, 02, 05, 09.
