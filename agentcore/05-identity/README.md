# 05 — Enforcing the customer's identity at the gateway with Policy in AgentCore

Extends the demo 04 agent with identity at both ends, done the way AWS's
Well-Architected Agentic AI Lens asks for. Inbound, the runtime and the
gateway both validate the customer's own token, so the caller is a known
Brightwell customer. The agent relays that token rather than minting its
own, and Policy in AgentCore evaluates a Cedar policy on every tool call at
the gateway, permitting a customer to list only their own orders and denying
anything else by default, before the tool runs and outside the agent's code.
Still no model in it; that is post 06.

Each demo in the series is independently deployable and carries the previous
one forward, so the gateway, the memory store and the sandbox are all here
too. They are not re-explained, the post they belong to covers them.

## What gets created

- Everything from demo 01 (ECR repo, runtime execution role, runtime),
  namespaced `demos-agentcore-05-identity-*`. The runtime has a
  `custom_jwt_authorizer` for the customers client and forwards the
  `Authorization` header
- Everything from demo 02, a Lambda behind an AgentCore Gateway with a
  Cognito pool. The gateway now validates the customer's token (its
  `allowed_clients` is the customers client), the pool has one public
  customers client with admin-only user creation, and the target exposes
  `list_orders` only
- A Policy Engine (`demos_agentcore_05_orders`) and two Cedar policies, a
  `permit` (`own_orders_only`) and a `forbid` guard
  (`deny_other_customers_orders`), attached to the gateway in `ENFORCE` mode
- Everything from demo 03 (memory) and demo 04 (Code Interpreter sandbox)
- No OAuth2 credential provider and no `GetResourceOauth2Token` call. The
  agent has no client secret or agent-owned gateway credential, though it
  handles the customer's short-lived bearer token and must treat it as
  sensitive. The gateway role gets the policy-engine read and evaluate actions

## Before you start, the state backend

`make demo-init` expects the shared state bucket and KMS key, created once
per account by [`aws-setup/`](../../aws-setup/README.md).

## Run it

From the repository root:

```bash
make demo-init demo-image demo-apply DEMO=agentcore/05-identity
cd agentcore/05-identity
```

NOTE: the apply that attaches the policy engine grants the gateway role new
permissions and then uses them in the same run, so it races IAM's eventual
consistency. If the first `demo-apply` fails with an access-denied on
`AuthorizeAction` or `PartiallyAuthorizeActions`, run it again; it succeeds
once the permissions propagate.

`demo-apply` defaults the policy engine to `ENFORCE`. `LOG_ONLY` mode records what the policy would decide but lets the call run,
so a denied call still returns the data. Use it only against synthetic data
in an isolated account, never against real customer data, and prefer keeping
this stack in `ENFORCE`.

Create a customer. Brightwell's customer ids are the pool's usernames, so
the username is a customer id from `tool/orders.csv`. Read the password from
the terminal so nothing in the repo or shell history holds it:

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

Sign in and call the agent. With a JWT authorizer the runtime is called over
HTTPS with the token:

```bash
TOKEN=$(aws-vault exec lev:andy.rea -- aws cognito-idp initiate-auth --region "$REGION" \
  --client-id "$CLIENT_ID" --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters USERNAME=c-1000,PASSWORD="$PASSWORD" \
  --query AuthenticationResult.AccessToken --output text)
unset PASSWORD

curl -s "$INVOKE_URL" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -H "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id: any-session-id-of-33-chars-or-more-05a" \
  -d '{"prompt": "list my orders"}'
```

To see the gateway enforce, call it directly with `probe_gateway.py`. It
needs the MCP client, so install it first (a virtualenv keeps it off the
system Python):

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install mcp==1.29.0
```

Your own customer id is allowed, anyone else's is denied by the policy:

```bash
GATEWAY_URL=$(cd terraform && aws-vault exec lev:andy.rea -- terraform state show \
  aws_bedrockagentcore_gateway.orders | sed -n 's/.*gateway_url *= *"\(.*\)"/\1/p')
GATEWAY_URL="$GATEWAY_URL" TOKEN="$TOKEN" python3 probe_gateway.py c-1000
GATEWAY_URL="$GATEWAY_URL" TOKEN="$TOKEN" python3 probe_gateway.py c-1001
```

## Notes kept out of the post

- The two Cognito commands take the password as an argument, so it is briefly
  visible in the local process table. That is the AWS walkthrough's shape and
  acceptable only in an isolated single-user demo account. Anywhere real,
  pass it through the SDK with `getpass` so it never reaches argv.

- `AuthorizeAction` and `PartiallyAuthorizeActions` do not support
  resource-level scoping, so the gateway role grants them on `*`. Which
  policy engine the gateway may read is still scoped, so this does not widen
  what it can evaluate.
- The Cedar policy's resource must name this gateway's ARN. A tool-specific
  action with a wildcard resource is refused by `CreatePolicy`.
- The gateway update that attaches the engine races IAM's eventual
  consistency on the new role permissions, so the first `apply` after adding
  them can fail with an access-denied and succeed on a retry.
- For a first-party AWS store, web-identity federation with STS and IAM is
  the enforcement, no policy engine needed. For a third-party SaaS, AgentCore
  Identity's on-behalf-of token exchange carries the delegation, which needs
  an RFC 8693 provider and so is not for Cognito. The post names both.

## Tear down

```bash
make demo-destroy DEMO=agentcore/05-identity
```

NOTE: stop any live code interpreter sessions first, a sandbox with active
sessions refuses to delete.
