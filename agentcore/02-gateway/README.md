# 02 — Giving your agent tools with AgentCore Gateway

Puts AgentCore Gateway in front of a plain Lambda (`lookup_order`) so the
agent can call it as an MCP tool, authenticated with a Cognito-issued JWT
that the gateway validates on every call. Copies demo 01 forward; the
delta is the Cognito pool, the gateway, target and tool Lambda plus the
agent's MCP client.

## What gets created

- Everything from demo 01 (ECR repo, runtime execution role, runtime),
  namespaced `demos-agentcore-02-gateway-*`
- Lambda `demos-agentcore-02-gateway-lookup-order` + role
- AgentCore Gateway `demos-agentcore-02-gateway-gw` (MCP, CUSTOM_JWT) and
  the `orders` Lambda target
- Cognito user pool, domain, resource server and `client_credentials` app
  client, with the client secret in Secrets Manager

## Auth choices

The post keeps this brief, so the reasoning is here.

**Why `CUSTOM_JWT` and not `NONE`.** A gateway is the first thing in this
series reachable from outside the account. Post 01's runtime sat behind the
AgentCore API, but a gateway is an HTTPS endpoint that invokes your Lambda.
`authorizer_type` is also immutable, so a gateway created with `NONE` has to
be destroyed and replaced to add auth later, not updated.

**Why not `AWS_IAM`.** It is the better fit when every caller is AWS, and it
has no secret anywhere because it uses the runtime role's own rotating
credentials. JWT was chosen because the Identity post builds on this pool,
and because it is the shape that keeps working when the caller is not AWS.
The cost is one long-lived client secret.

**Where that secret lives.** Secrets Manager, read by the runtime execution
role, so it is out of the image and out of the environment. It is also in
Terraform state, because the provider reads
`aws_cognito_user_pool_client.client_secret` back as a computed attribute, and there is no write-only or ephemeral variant
to suppress it. The Secrets Manager version itself uses `secret_string_wo`,
so that copy stays out of state, but the app client's does not. Hence the
encrypted state bucket in [`aws-setup/`](../../aws-setup/README.md).

**Rotation.** Cognito supports two concurrent client secrets at the API
level, but the Terraform provider does not implement it yet
([hashicorp/terraform-provider-aws#46809](https://github.com/hashicorp/terraform-provider-aws/issues/46809)),
so rotating today means replacing the app client and updating
`allowed_clients` on the gateway.

**Where the IAM is looser than least privilege.** The gateway role's
identity policy allows `lambda:InvokeFunction` on exactly one function ARN,
but its trust policy is broader, the `aws:SourceArn` condition matches any
AgentCore resource in the account rather than this gateway alone, so control
who can pass the role. The runtime role also needs
`ecr:GetAuthorizationToken` on `*`, because ECR gives no way to scope it.

**The client is stock, but only because of JWT.** The MCP SDK handles
framing and transport, and with `CUSTOM_JWT` that is all you need, since the
credential is an ordinary `Authorization` header. An `AWS_IAM` gateway
expects SigV4 and the MCP client signs nothing for you, so that route needs
an AWS-aware layer such as `mcp-proxy-for-aws`. What you should not do
either way is reach into `botocore.auth` and assemble signed requests by
hand, which reimplements a supported integration with private APIs.

**Token handling.** `access_token()` caches the token until shortly before
expiry, behind a lock, because the runtime is a threaded HTTP server and a
burst of requests at expiry would otherwise each pay a Secrets Manager read
and a token round trip.

**Authenticated is not authorised.** Every call carries the same workload
identity. The gateway establishes that a legitimate client is calling, not
that it may see a particular order. Anything user- or tenant-specific needs
the caller's identity carried through and a check in the backend.

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
make demo-init demo-image demo-apply DEMO=agentcore/02-gateway
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
