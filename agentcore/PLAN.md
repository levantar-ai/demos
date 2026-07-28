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
- [x] Post published and listed on the homepage (2026-07-24), with video,
  social cards (1200x627 og:image + 1200x1200 square) and clickable links

### 02 — Giving your agent tools with AgentCore Gateway
APIs and Lambdas as MCP tools via Gateway targets.
Demo: the agent answers order questions via a Lambda behind a Gateway
target, with Cognito client-credentials JWT auth.
- [x] Demo built (`02-gateway/`)
- [x] Demo deployed and invoked end to end (agent → token → gateway →
  Lambda); artifacts in `02-gateway/artifacts/`; resources destroyed after
- [x] Post drafted (`02-gateway/POST.md`); live as an unlisted preview
  with video and social cards; externally reviewed twice (incl. the
  AWS_IAM no-secrets rework)
- [ ] Post listed on the homepage (awaiting Andy's approval)

### 03 — Short-term and long-term memory
Session context vs. extracted long-term memory, strategies, namespaces.
Demo: agent recalls user preferences across separate sessions.
- [x] Demo built (`03-memory/`)
- [x] Demo deployed and invoked end to end (events stored session A,
  extracted USER_PREFERENCE records recalled from session B); artifacts in
  `03-memory/artifacts/`; video recorded; resources destroyed after
- [x] Post drafted (`03-memory/POST.md`); live as an unlisted preview
  with video and social cards; externally reviewed
- [ ] Post listed on the homepage (awaiting Andy's approval)

### 04 — Letting an agent run code, without letting it run loose
Code Interpreter sandbox; the security model of agent-run code.
Demo: agent analyses a caller-supplied CSV with pandas inside a SANDBOX
session, with the isolation (no network, no credentials) probed directly.
- [x] Demo built (`04-builtin-tools/`)
- [x] Demo deployed and invoked; sandbox isolation probed; artifacts in
  `04-builtin-tools/artifacts/`; video recorded; resources destroyed after
- [x] Post drafted (`04-builtin-tools/POST.md`); live as an unlisted
  preview with video and social cards
- [x] Externally reviewed (gpt-5.6): six findings, all actioned and
  re-verified live (session leak fixed, stream errors surfaced, body
  capped, framing and probe claims corrected)
- [ ] Post listed on the homepage (awaiting Andy's approval)

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

## Per-post definition of done

1. Standalone demo dir (agent + contract tests, namespaced terraform,
   diagram.py, demo.tape, README, POST.md, artifacts/); copies the
   previous demo forward, the delta is the post's topic.
2. Local gates: pytest (incl. invalid-JSON / non-object / type-guard
   cases), pinned ruff, terraform fmt + validate, cspell.
3. Security, nothing to critique: no static or application-managed
   credentials anywhere (role-based IAM SigV4 by default; AgentCore
   Identity or Secrets Manager if a secret is unavoidable);
   least-privilege IAM with exact ARNs shown in the post as code;
   SourceAccount + SourceArn on service trust policies; non-root
   containers; pinned direct dependencies; generic client errors with
   detail logged server-side; every security claim quoted from AWS docs.
4. Deployed and tested for real: every output in the post captured from a
   live run, negative paths exercised (401/400), evidence in
   artifacts/README.md, everything destroyed after and the account
   verified empty.
5. Reviewed twice: internal adversarial panel (AWS facts, code/prose
   consistency, voice), then gpt-5.6 via the OpenAI API; findings
   verified against the real service before accepting; accepted fixes
   redeployed and retested; re-review on material implementation change.
6. Content: voice per ~/.claude/andy-rea-voice.md, happy path only,
   NOTEs for blockers, no teardown sections; diagram PNG committed;
   video recorded at the exact final commit with a real apply on camera,
   clean poster, and narrative coherence, frame-verified; social cards
   in both formats (1200x627 wired as og:image, 1200x1200 square for
   native feed posts) published with the page; page published unlisted
   until Andy approves listing.
7. Everything lands via a PR with CI green; PLAN.md ticked; the live
   page verified serving the change.

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
