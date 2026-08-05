# 04 — Letting an agent run code, without letting it run loose

Extends the demo 03 agent with a managed Python sandbox (AgentCore Code Interpreter) and
has it analyse a caller-supplied CSV with pandas inside that sandbox,
rather than parsing untrusted input in the agent's own microVM.

Each demo in the series is independently deployable and carries the
previous one forward, so the gateway, its Cognito pool and the tool
Lambda are all here too. They are not re-explained, the post they
belong to covers them.

## What gets created

- Everything from demo 01 (ECR repo, runtime execution role, runtime),
  namespaced `demos-agentcore-04-builtin-tools-*`
- Everything from demo 02, so the tool path still works here, a Lambda
  behind an AgentCore Gateway with a Cognito pool issuing the JWT the
  gateway validates. Post 02 covers it, this demo just carries it forward
- Everything from demo 03, an AgentCore Memory store and its
  `UserPreferences` strategy, again carried forward rather than
  re-explained
- Code Interpreter `demos_agentcore_04_interpreter` in `SANDBOX` network
  mode (no network access from the sandbox at all)
- Runtime role scoped to three actions on that one sandbox

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

```bash
make demo-init demo-apply DEMO=agentcore/04-builtin-tools
```

Analyse a CSV:

```bash
aws-vault exec lev:andy.rea -- aws bedrock-agentcore invoke-agent-runtime \
  --cli-binary-format raw-in-base64-out \
  --agent-runtime-arn "$(cd terraform && terraform output -raw runtime_arn)" \
  --runtime-session-id "any-session-id-of-33-chars-or-more-04a" \
  --payload file://payload.json --region us-east-1 /dev/stdout
```

## Tear down

```bash
make demo-destroy DEMO=agentcore/04-builtin-tools
```

NOTE: stop any live code interpreter sessions first, a sandbox with
active sessions refuses to delete.
