# 02 — Giving your agent tools with AgentCore Gateway

Puts AgentCore Gateway in front of a plain Lambda (`lookup_order`) so the
agent can call it as an MCP tool, with Cognito client-credentials issuing
the JWTs the gateway's authorizer requires. Copies demo 01 forward; the
delta is the gateway, target, tool Lambda and Cognito resources plus the
agent's MCP client functions.

## What gets created

- Everything from demo 01 (ECR repo, runtime execution role, runtime),
  namespaced `demos-agentcore-02-gateway-*`
- Lambda `demos-agentcore-02-gateway-lookup-order` + role
- Cognito user pool, domain, resource server (`demos-gateway/invoke`) and
  client-credentials app client
- AgentCore Gateway `demos-agentcore-02-gateway-gw` (MCP, CUSTOM_JWT) and
  the `orders` Lambda target

## Run it

```bash
make demo-init demo-apply DEMO=agentcore/02-gateway
```

Ask it something:

```bash
aws-vault exec lev:andy.rea -- aws bedrock-agentcore invoke-agent-runtime \
  --cli-binary-format raw-in-base64-out \
  --agent-runtime-arn "$(cd terraform && terraform output -raw runtime_arn)" \
  --runtime-session-id "any-session-id-of-33-chars-or-more-001" \
  --payload '{"prompt": "where is order 42?"}' --region us-east-1 /dev/stdout
```

## Tear down

```bash
make demo-destroy DEMO=agentcore/02-gateway
```
