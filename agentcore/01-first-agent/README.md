# 01 — Your first agent on AgentCore Runtime

Deploys a minimal HTTP-contract agent (`POST /invocations`, `GET /ping`) as a
container to Amazon Bedrock AgentCore Runtime. This is the baseline every later
demo in the series copies forward.

## What gets created

- ECR repository `demos/agentcore/01-first-agent` (image built by CI for
  `linux/arm64`, tagged with the git SHA)
- IAM execution role `demos-agentcore-01-first-agent-runtime`
- AgentCore Runtime `demos_agentcore_01_first_agent`

## Run it

Deployed automatically by CI when this directory changes on `main`. Locally:

```bash
make demo-init demo-apply DEMO=agentcore/01-first-agent
```

Invoke:

```bash
aws-vault exec lev:andy.rea -- aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn "$(cd terraform && terraform output -raw runtime_arn)" \
  --payload '{"prompt": "hello"}' --region us-east-1 /dev/stdout
```

## Tear down

```bash
make demo-destroy DEMO=agentcore/01-first-agent
```
