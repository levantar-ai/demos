# 05 — Knowing who your agent is acting for, with AgentCore Identity

Extends the demo 04 agent with identity at both ends. Inbound, the runtime
has a JWT authorizer against the Cognito pool, so every caller is a
Brightwell customer with a token and the agent takes the customer from the
verified claims rather than from the request body. Outbound, the agent's
own client credentials move into AgentCore Identity's token vault, and the
agent asks it for a gateway token instead of reading a secret and minting
one. Still no model in it, that is post 06.

Each demo in the series is independently deployable and carries the
previous one forward, so the gateway, the memory store and the sandbox
are all here too. They are not re-explained, the post they belong to
covers them.

## What gets created

- Everything from demo 01 (ECR repo, runtime execution role, runtime),
  namespaced `demos-agentcore-05-identity-*`. The runtime now has a
  `custom_jwt_authorizer` allowing the customers' app client and forwards
  the `Authorization` header to the container
- Everything from demo 02, a Lambda behind an AgentCore Gateway with a
  Cognito pool issuing the JWT the gateway validates. The pool gains a
  second app client, `demos-agentcore-05-identity-customers`, with no
  secret and `USER_PASSWORD_AUTH`, for customers, and only admins can
  create users, so nobody can register a customer id before its owner.
  The target now exposes `list_orders` only. Post 02's `lookup_order`
  answered for any order id to whoever held the agent's token, and nothing
  acting for a customer has a use for it
- Everything from demo 03 (memory store and `UserPreferences` strategy)
  and demo 04 (Code Interpreter in `SANDBOX` mode)
- An OAuth2 credential provider, `demos-agentcore-05-identity-gateway`,
  holding the agent client's id and secret write-only. The Secrets Manager
  secret from demo 02 is gone
- Runtime role scoped to `GetResourceOauth2Token` on that provider and
  this runtime's workload identity, plus `GetSecretValue` on the secret
  the vault keeps the client secret in

## Before you start, the state backend

`make demo-init` expects the shared state bucket and KMS key to exist. They
are created once per account by [`aws-setup/`](../../aws-setup/README.md),
which is a one-time bootstrap, not part of this demo.

State for these demos is not inert, the Cognito app client secret is in
it as a computed attribute, so the bucket is encrypted with a customer
managed key and denies non-TLS and unencrypted writes.

## Run it

From the repository root:

```bash
make demo-init demo-image demo-apply DEMO=agentcore/05-identity
cd agentcore/05-identity
```

Create a customer. Brightwell's customer ids are the pool's usernames, so
the username is the customer id from `tool/orders.csv`. The password has
to meet Cognito's default policy, and reading it from the terminal keeps
it out of the shell history:

```bash
REGION=$(cd terraform && aws-vault exec lev:andy.rea -- terraform output -raw aws_region)
POOL=$(cd terraform && aws-vault exec lev:andy.rea -- terraform output -raw user_pool_id)
CLIENT_ID=$(cd terraform && aws-vault exec lev:andy.rea -- terraform output -raw customers_client_id)
INVOKE_URL=$(cd terraform && aws-vault exec lev:andy.rea -- terraform output -raw invoke_url)
read -rsp "Customer password: " PASSWORD; echo

aws-vault exec lev:andy.rea -- aws cognito-idp admin-create-user --region "$REGION" \
  --user-pool-id "$POOL" --username c-1000 --message-action SUPPRESS
aws-vault exec lev:andy.rea -- aws cognito-idp admin-set-user-password --region "$REGION" \
  --user-pool-id "$POOL" --username c-1000 --password "$PASSWORD" --permanent
```

Sign in as the customer and call the runtime with the token. With a JWT
authorizer the runtime is called over HTTPS with a bearer token, the
SigV4-signed CLI no longer applies:

```bash
TOKEN=$(aws-vault exec lev:andy.rea -- aws cognito-idp initiate-auth --region "$REGION" \
  --client-id "$CLIENT_ID" --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters USERNAME=c-1000,PASSWORD="$PASSWORD" \
  --query AuthenticationResult.AccessToken --output text)
unset PASSWORD

curl -s "$INVOKE_URL" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id: any-session-id-of-33-chars-or-more-05a" \
  -d '{"prompt": "list my orders"}'
```

Expect c-1000's seven orders. `where is order 1255?` returns that order,
`where is order 1014?` says it is not on your account, `remember: ...`
and `recap` work as in post 03 with the customer as the actor, and posting
`payload.json` runs the post 04 analysis in the sandbox. Without a token
the service answers 401 before the agent is involved.

## Notes kept out of the post

- The two Cognito commands take the password as an argument, so it is
  visible in the local process table while they run. That is the AWS
  walkthrough's own shape and fine on a workstation; a provisioning
  pipeline would use `--cli-input-json` from a file descriptor instead.

- The gateway and the Lambda behind it still only know the agent's
  identity. Scoping to the customer happens in the agent, which is fine
  while the agent's code chooses the arguments and is the boundary to
  think about once a model does.
- The vault stores the client secret in a Secrets Manager secret named
  `bedrock-agentcore-identity!default/oauth2/<provider>-...` and reads it
  with the caller's role. The provider exports that ARN as
  `client_secret_arn`, which is what the IAM statement grants.
- The runtime treats a 5xx from the container on a fresh session as a
  failed initialisation. It retries the POST every couple of seconds and
  after 120s the caller gets `HTTP 424 Runtime initialization time
  exceeded`, so a misconfigured agent looks like a slow start rather than
  an error. The container's own logs have the real reason.
- A malformed bearer token gets `403 OAuth authorization failed: Failed to
  parse token`. A well-formed token from the wrong client gets `401 Claim
  'client_id' value mismatch with configuration`.
- Third-party consent (Google, GitHub, and so on) is the same
  `get_resource_oauth2_token` call with `oauth2Flow="USER_FEDERATION"`,
  which returns an authorization URL for the customer the first time and
  the vaulted token after that. It needs an OAuth app registered with the
  provider and a callback URL on the workload identity, so it is not built
  here.

## Tear down

```bash
make demo-destroy DEMO=agentcore/05-identity
```

NOTE: stop any live code interpreter sessions first, a sandbox with
active sessions refuses to delete.
