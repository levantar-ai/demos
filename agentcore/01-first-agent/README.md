# 01 — Your first agent on AgentCore Runtime

Deploys a minimal HTTP-contract agent (`POST /invocations`, `GET /ping`) as a
container to Amazon Bedrock AgentCore Runtime. This is the baseline every later
demo in the series copies forward.

## What gets created

- ECR repository `demos/agentcore/01-first-agent` (image is `linux/arm64`,
  tagged with the git SHA; tags are immutable)
- IAM execution role `demos-agentcore-01-first-agent-runtime`
- AgentCore Runtime `demos_agentcore_01_first_agent`

## Before you start, the state backend

`make demo-init` expects the shared state bucket and KMS key to exist. They
are created once per account by [`aws-setup/`](../../aws-setup/README.md),
which is a one-time bootstrap, not part of this demo.

State for these demos is not inert, post 02 puts a Cognito app client secret
in it, so the bucket is encrypted with a customer managed key and denies
non-TLS and unencrypted writes. Set it up first:

```bash
# see aws-setup/README.md for the one-time bootstrap
terraform -chdir=aws-setup apply
```

## Run it

CI only verifies this demo (tests, quality, security). Deployment is local:

```bash
make demo-init demo-image demo-apply DEMO=agentcore/01-first-agent
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
