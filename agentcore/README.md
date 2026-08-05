# AgentCore demo series

Demos accompanying the blog series on Amazon Bedrock AgentCore. Each post has
its own directory here, and **every demo is fully standalone**: clone the repo,
`cd` into one directory, and deploy it without touching any other demo. Later
posts copy the previous demo forward and add their delta, so the blog post is
the diff between the two directories. Everything carried forward stays working,
it just is not re-explained, the post it belongs to covers it.

## Series

| # | Demo | Post | What it adds |
|---|------|------|--------------|
| 01 | [`01-first-agent/`](01-first-agent/) | [read →](01-first-agent/POST.md) | A minimal agent deployed to AgentCore Runtime |
| 02 | [`02-gateway/`](02-gateway/) | [read →](02-gateway/POST.md) | Tools via AgentCore Gateway, authenticated with Cognito |
| 03 | [`03-memory/`](03-memory/) | [read →](03-memory/POST.md) | Short- and long-term memory |
| 04 | [`04-builtin-tools/`](04-builtin-tools/) | [read →](04-builtin-tools/POST.md) | Code Interpreter sandbox |
| 05 | `05-identity/` *(planned)* | | Inbound/outbound auth |
| 06 | `06-observability/` *(planned)* | | Tracing and debugging |
| 07 | `07-evals/` *(planned)* | | Evals: testing agent behaviour as a quality gate |
| 08 | `08-multi-agent/` *(planned)* | | Supervisor/worker topologies |
| 09 | `09-cost/` *(planned)* | | Cost modelling |
| 10 | `10-case-study/` *(planned)* | | The finished system |

## Conventions (namespacing)

All demos share one AWS account and must coexist:

- **AWS resources:** `demos-agentcore-<demo>-…` (runtime names use `_` per
  AgentCore constraints, e.g. `demos_agentcore_01_first_agent`)
- **ECR repositories:** `demos/agentcore/<demo>`
- **Terraform state keys:** `terraform/demos/agentcore/<demo>/terraform.tfstate`
- **Log groups:** `/aws/bedrock-agentcore/…` (created by the service)
- **Region:** `us-east-1` (AgentCore); state bucket lives in `eu-west-2`

## CI vs deployment

CI (**verification only**) runs tests, quality and security gates for every
demo, terraform validate + tflint + Trivy (misconfig/secrets), ruff + pytest
(or go vet/test) for agent code, and an arm64 container build check. Changed
demos are verified on PRs; all demos on `main`.

Deployment is **out-of-band**, always run locally:

```bash
make demo-init  DEMO=agentcore/01-first-agent
make demo-plan  DEMO=agentcore/01-first-agent
make demo-apply DEMO=agentcore/01-first-agent
make demo-destroy DEMO=agentcore/01-first-agent
```

## Structure of a demo

```
agentcore/<nn-name>/
├── agent/          # container the runtime executes (Dockerfile + code)
├── terraform/      # standalone stack, ECR, IAM and AgentCore resources
└── README.md       # what the post demonstrates, how to run it
```
