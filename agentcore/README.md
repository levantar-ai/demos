# AgentCore demo series

Demos accompanying the blog series on Amazon Bedrock AgentCore. Each post has
its own directory here, and **every demo is fully standalone**: clone the repo,
`cd` into one directory, and deploy it without touching any other demo. Later
posts copy the previous demo forward and add their delta — the blog post shows
the diff between the two directories.

## Series

| # | Demo | What it adds |
|---|------|--------------|
| 01 | [`01-first-agent/`](01-first-agent/) | A minimal agent deployed to AgentCore Runtime |
| 02 | *(the pipeline itself — see `.github/workflows/deploy-demos.yml`)* | Terraform + GitHub OIDC deployment |
| 03 | `03-gateway/` *(planned)* | Tools via AgentCore Gateway |
| 04 | `04-memory/` *(planned)* | Short- and long-term memory |
| 05 | `05-builtin-tools/` *(planned)* | Code Interpreter + Browser |
| 06 | `06-identity/` *(planned)* | Inbound/outbound auth |
| 07 | `07-observability/` *(planned)* | Tracing and debugging |
| 08 | `08-ci-evals/` *(planned)* | Testing and evals in CI |
| 09 | `09-multi-agent/` *(planned)* | Supervisor/worker topologies |
| 10 | `10-cost/` *(planned)* | Cost modelling |
| 11 | `11-case-study/` *(planned)* | The finished system |

## Conventions (namespacing)

All demos share one AWS account and must coexist:

- **AWS resources:** `demos-agentcore-<demo>-…` (runtime names use `_` per
  AgentCore constraints, e.g. `demos_agentcore_01_first_agent`)
- **ECR repositories:** `demos/agentcore/<demo>`
- **Terraform state keys:** `terraform/demos/agentcore/<demo>/terraform.tfstate`
- **Log groups:** `/aws/bedrock-agentcore/…` (created by the service)
- **Region:** `us-east-1` (AgentCore); state bucket lives in `eu-west-2`

## Deploy / tear down

CI deploys any demo whose files change on `main` (see the workflow). Locally:

```bash
make demo-init  DEMO=agentcore/01-first-agent
make demo-plan  DEMO=agentcore/01-first-agent
make demo-apply DEMO=agentcore/01-first-agent
# out-of-band teardown:
make demo-destroy DEMO=agentcore/01-first-agent
```

## Structure of a demo

```
agentcore/<nn-name>/
├── agent/          # container the runtime executes (Dockerfile + code)
├── terraform/      # standalone stack: ECR, IAM, AgentCore resources
└── README.md       # what the post demonstrates, how to run it
```
