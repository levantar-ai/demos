# AgentCore blog series — plan and progress

Eleven posts on Amazon Bedrock AgentCore, each with a working demo in this
repo. Every demo is standalone; later demos copy the previous one forward and
the post shows the diff. Tick items as they complete.

## Repo foundations

- [x] `agentcore/` category structure (one standalone dir per post)
- [x] CI pipeline (verification only): per-demo tests + quality + security
  (terraform validate, tflint, Trivy, ruff, pytest/go test, arm64 build check)
- [x] `aws-setup/` applied: OIDC role exists but CI does NOT deploy —
  all deploys/teardowns are run locally via the Makefile
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

### 02 — Deploying AgentCore with Terraform and GitHub OIDC
The pipeline itself is the demo: OIDC trust, namespaced state keys, quality
gates, per-demo change detection, plan-on-PR / apply-on-main.
- [x] Demo exists (this repo's `aws-setup/` + workflow)
- [ ] Pipeline demonstrated end to end
- [ ] Post drafted
- [ ] Post published

### 03 — Giving your agent tools with AgentCore Gateway
APIs and Lambdas as MCP tools via Gateway targets; semantic tool search.
Demo: the agent answers questions it couldn't before, via a Gateway target.
- [ ] Demo built (`03-gateway/`)
- [ ] Demo deployed and invocable
- [ ] Post drafted
- [ ] Post published

### 04 — Short-term and long-term memory
Session context vs. extracted long-term memory, strategies, namespaces.
Demo: agent recalls user preferences across separate sessions.
- [ ] Demo built (`04-memory/`)
- [ ] Demo deployed and invocable
- [ ] Post drafted
- [ ] Post published

### 05 — Code Interpreter and Browser built-in tools
Sandboxed execution and cloud browser; the security model of agent-run code.
Demo: agent analyses an uploaded CSV and completes a live web task.
- [ ] Demo built (`05-builtin-tools/`)
- [ ] Demo deployed and invocable
- [ ] Post drafted
- [ ] Post published

### 06 — Identity: who is your agent acting as?
Inbound auth (Cognito/OIDC) and outbound OAuth token vaulting.
Demo: agent accesses a user's GitHub/Google account on their behalf, with
consent flow.
- [ ] Demo built (`06-identity/`)
- [ ] Demo deployed and invocable
- [ ] Post drafted
- [ ] Post published

### 07 — Observability: tracing an agent's reasoning
OTEL traces through Runtime/Gateway/Memory in CloudWatch; session debugging.
Demo: debug a deliberately-broken agent run via its trace.
- [ ] Demo built (`07-observability/`)
- [ ] Demo deployed and invocable
- [ ] Post drafted
- [ ] Post published

### 08 — Testing and evaluating agents in CI
Tool contract tests, mocked-model units, LLM-as-judge evals as a gate.
Demo: a PR fails CI because an eval regressed, then passes after a fix.
- [ ] Demo built (`08-ci-evals/`)
- [ ] Demo deployed and invocable
- [ ] Post drafted
- [ ] Post published

### 09 — Multi-agent patterns on AgentCore
Supervisor/worker, agents calling agents, A2A vs. MCP, and when multi-agent
is warranted. Demo: split the series agent into a supervisor plus two
specialists.
- [ ] Demo built (`09-multi-agent/`)
- [ ] Demo deployed and invocable
- [ ] Post drafted
- [ ] Post published

### 10 — Cost, quotas, and the bill nobody modelled
Consumption pricing; session duration and memory strategy as cost drivers.
Demo: cost dashboard/script pulling real spend from the series agents and
projecting at 10k sessions/month.
- [ ] Demo built (`10-cost/`)
- [ ] Demo deployed and invocable
- [ ] Post drafted
- [ ] Post published

### 11 — Case study: from prototype to production
Retrospective: the finished architecture, what AgentCore saved, where it
fought back, and a decision framework. Demo: end-to-end walkthrough of the
finished system.
- [ ] Demo built (`11-case-study/`)
- [ ] Demo deployed and invocable
- [ ] Post drafted
- [ ] Post published

## Notes

- Differentiator posts (least covered elsewhere): 02, 06, 08, 10.
- AgentCore moves fast — pin SDK/provider versions in each demo and state the
  version in each post.
- Trimmed six-post version if needed: 01, 02, 03, 06, 10.
