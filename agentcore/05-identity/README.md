# 05 — The agent's token for the order service, brokered by AgentCore Identity

Extends the demo 04 agent with identity at both ends. Inbound, the runtime
validates the customer's own Cognito token, so the caller is a known
Brightwell customer. Outbound, the agent does not relay that token. It asks
AgentCore Identity for a token for the order service on the customer's
behalf, the on-behalf-of exchange, and AgentCore Identity brokers one from the
customer's token that a second Cognito pool mints, for the audience the
gateway is configured to accept and five minutes long. Cognito's token endpoint does not offer
the RFC 8693 grant, so the exchange is built the way AWS's
`sample-cognito-oauth2-token-exchange` builds it: a small front door
implements the grant and the exchange pool's triggers verify the customer's
token and mint. The gateway trusts that pool and Policy in AgentCore
evaluates a Cedar policy on every tool call, permitting `list_orders` only
when its `customer_id` matches the `customer_id` claim in the presented
token. It does not bind that token to the current runtime invocation; the
post says what that leaves open. Still no model in it; that is post 06.

Each demo in the series is independently deployable and carries the previous
one forward, so the gateway, the memory store and the sandbox are all here
too. They are not re-explained, the post they belong to covers them.

## What gets created

- Everything from demo 01 (ECR repo, runtime execution role, runtime),
  namespaced `demos-agentcore-05-identity-*`. The runtime has a
  `custom_jwt_authorizer` for the customers client and forwards the
  `Authorization` header
- Everything from demo 02, a Lambda behind an AgentCore Gateway with a
  Cognito pool. The pool has one public customers client with admin-only user
  creation, and the target exposes `list_orders` only. The gateway's
  authorizer now trusts the exchange pool, by `allowed_audience` set to its
  orders app client, and does not accept a customer-pool token at all
- The AgentCore Identity resources: an explicit workload identity
  (`demos_agentcore_05_agent`) and an OAuth2 credential provider
  (`demos_agentcore_05_obo`) configured for on-behalf-of exchange, created
  through Cloud Control because the AWS provider's resource does not model it.
  The runtime role gains `GetWorkloadAccessTokenForJWT`,
  `GetResourceOauth2Token` and `GetSecretValue` on the provider's managed secret
- The exchange, the OBO target: the front door, one Lambda behind an HTTP API
  (`/token`, `/authorize`, a discovery document for the provider), and the
  exchange pool (`demos-agentcore-05-identity-exchange-pool`, Essentials
  tier) with its confidential `orders` app client (custom auth only, 5-minute
  tokens), its service user `orders-agent`, and four trigger Lambdas
  (`define`, `create`, `verify`, `pretoken`). Two secrets in Secrets Manager,
  the front door's client secret and the app client's, and one SSM parameter
  the functions read the pool ids from. All five functions share one package
  bundled at apply time by a `local-exec` pip install
- A Policy Engine (`demos_agentcore_05_orders`) and two Cedar policies, a
  `permit` (`own_orders_only`) and a `forbid` guard
  (`deny_other_customers_orders`), attached to the gateway in `ENFORCE` mode
- Everything from demo 03 (memory) and demo 04 (Code Interpreter sandbox)

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
once the permissions propagate. The exchange has the same shape of race: the
exchange pool's permission to invoke its triggers is created in the same
run, and the first exchange within a minute or two of the apply can come
back `invalid_grant` before any trigger ran. Retry it; nothing is wrong.

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

The gateway only accepts a token the exchange pool mints, which the agent
obtains through AgentCore Identity. To probe, exchange the customer's Cognito
token at the exchange service directly. Two credentials pass through `curl`'s
process arguments here, the provider's client secret from Secrets Manager and
the customer's bearer token, and the minted token lands in a shell variable.
That is acceptable only in an isolated single-user demo account with synthetic
data; anywhere real, drive the exchange from a script that reads them from
memory, never argv:

```bash
ISSUER=$(cd terraform && aws-vault exec lev:andy.rea -- terraform output -raw exchange_issuer)
SECRET=$(aws-vault exec lev:andy.rea -- aws secretsmanager get-secret-value --region "$REGION" \
  --secret-id demos-agentcore-05-identity-exchange-client --query SecretString --output text \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["client_secret"])')
MINTED=$(curl -s -u "brightwell-orders-agent:$SECRET" "$ISSUER/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=urn:ietf:params:oauth:grant-type:token-exchange" \
  --data-urlencode "subject_token=$TOKEN" \
  --data-urlencode "subject_token_type=urn:ietf:params:oauth:token-type:jwt" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
```

Your own customer id is allowed, anyone else's is denied by the policy, and
the raw customer-pool token is refused outright:

```bash
GATEWAY_URL=$(cd terraform && aws-vault exec lev:andy.rea -- terraform state show \
  aws_bedrockagentcore_gateway.orders | sed -n 's/.*gateway_url *= *"\(.*\)"/\1/p')
GATEWAY_URL="$GATEWAY_URL" TOKEN="$MINTED" python3 probe_gateway.py c-1000
GATEWAY_URL="$GATEWAY_URL" TOKEN="$MINTED" python3 probe_gateway.py c-1001
GATEWAY_URL="$GATEWAY_URL" TOKEN="$TOKEN"  python3 probe_gateway.py c-1000   # 403
unset SECRET MINTED TOKEN
```

## Notes kept out of the post

- The two Cognito commands take the password as an argument, so it is briefly
  visible in the local process table. That is the AWS walkthrough's shape and
  acceptable only in an isolated single-user demo account. Anywhere real,
  pass it through the SDK with `getpass` so it never reaches argv.

- `AuthorizeAction` and `PartiallyAuthorizeActions` do not support
  resource-level scoping, so the gateway role grants them on `*`, and that
  is account-wide. The read actions on the engine are scoped to this one,
  but scoping them does not restrict what those two evaluation actions can
  be asked to evaluate.
- The Cedar policy's resource must name this gateway's ARN. A tool-specific
  action with a wildcard resource is refused by `CreatePolicy`.
- The gateway update that attaches the engine races IAM's eventual
  consistency on the new role permissions, so the first `apply` after adding
  them can fail with an access-denied and succeed on a retry.

## Tear down

```bash
make demo-destroy DEMO=agentcore/05-identity
```

NOTE: stop any live code interpreter sessions first, a sandbox with active
sessions refuses to delete.
