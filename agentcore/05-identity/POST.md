# Knowing who your agent is acting for, with AgentCore Identity

## TL;DR;

How to put a JWT authorizer on an AgentCore Runtime so every caller is a
known customer, have the agent take that identity from the verified token
rather than the request body, and move the agent's own credentials into
AgentCore Identity's token vault so the agent's code never handles a
secret.

> SOURCE CODE - All code for this post is available at:
> https://github.com/levantar-ai/demos/tree/main/agentcore/05-identity

## Longer version

This series is building one thing, the order support agent for
Brightwell, a small online retailer of outdoor kit that ships with DPD and
Royal Mail. Posts 01 to 04 gave it a runtime, a tool that looks orders up,
memory and a sandbox. None of them knew who was asking.

That was deliberate, and it left two gaps that were flagged as they went
past. Post 02 noted that every call to the gateway carried the same
workload identity, so the gateway established that a legitimate client was
calling, not that it was entitled to a particular order. Post 03 took the
memory actor straight from the request body, with a note that a real
application maps it from an identity the workload has actually verified.
Until now, anyone who could invoke the runtime could say they were anyone.

This post closes both. Inbound, the runtime validates a customer's bearer
token before the agent sees the request, and the agent takes the customer
from the token's claims. Outbound, the agent stops holding a client secret
to reach the gateway and asks AgentCore Identity for a token instead. Both
halves are the precondition for the next post, where a model is handed
these tools and has to act as a known customer rather than as a string the
caller supplied.

![Architecture](architecture.png)

## 1 - Inbound, the runtime checks the caller

The Cognito pool from post 02 gains a second app client. The agent's
client is a machine with a secret and the `client_credentials` grant.
Customers are people, so their client has no secret and signs in with a
password:

```hcl
resource "aws_cognito_user_pool_client" "customers" {
  name         = "${local.name_prefix}-customers"
  user_pool_id = aws_cognito_user_pool.agents.id

  generate_secret     = false
  explicit_auth_flows = ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
}
```

The runtime then gets a JWT authorizer pointed at the pool's discovery
document, allowing only that client, and is told to forward the
`Authorization` header to the container:

```hcl
authorizer_configuration {
  custom_jwt_authorizer {
    discovery_url   = local.discovery_url
    allowed_clients = [aws_cognito_user_pool_client.customers.id]
  }
}

request_header_configuration {
  request_header_allowlist = ["Authorization"]
}
```

From here the runtime checks the signature, issuer, expiry and client id
of every bearer token before a request reaches the agent. A missing token
gets a 401 from the service, a valid token from the wrong client gets a
401 naming the mismatched claim, and IAM SigV4 invocation is off, a
runtime accepts one method or the other.

> NOTE: the allowlist is what makes the token visible to the agent. Without
> it the runtime still validates the token, but the container never sees
> it and the agent has no way of knowing who called.

## 2 - The agent reads who is calling

Brightwell's customer ids are the usernames in the pool, so the access
token's `username` claim is the customer id. The agent decodes the payload
and takes the customer from there:

```python
def claims_from(headers):
    auth = headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        payload = auth[len("Bearer "):].split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, ValueError):
        return None
    return claims if isinstance(claims, dict) else None


def customer_from(headers):
    username = (claims_from(headers) or {}).get("username")
    return username if isinstance(username, str) and username else None
```

Decoding without verifying is the documented pattern here. The runtime has
already done the verification, nothing reaches the container except
through the runtime, and AWS's
[own walkthrough](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-oauth.html)
says as much:

> You can skip validating the token signature here because AgentCore
> Runtime has already validated the token during inbound authorization.

A request that arrives without a usable token still gets a 401 from the
agent. That should never happen, and the check is there so a
misconfiguration fails loudly rather than defaulting to anyone.

Every route from posts 02 and 03 now takes the customer from that claim.
`remember` and `recap` use it as the memory actor, and the `actor` field
in the request body is gone. Order questions resolve through the customer's
own orders, so an order id from another account is not found rather than
looked up:

```python
def find_order(order_id, customer, workload_token):
    listed = json.loads(list_orders(customer, workload_token))
    for order in listed.get("orders", []):
        if str(order.get("order_id")) == str(order_id):
            return order
    return {"error": f"order {order_id} is not on your account"}
```

## 3 - Outbound, the agent's own credentials

Since post 02 the agent has read its Cognito client secret from Secrets
Manager and minted its own gateway token. AgentCore Identity takes that
over. An OAuth2 credential provider holds the client's credentials in the
token vault, and Terraform sends them write-only, so they are never
persisted in state:

```hcl
resource "aws_bedrockagentcore_oauth2_credential_provider" "gateway" {
  name                       = "${local.name_prefix}-gateway"
  credential_provider_vendor = "CustomOauth2"

  oauth2_provider_config {
    custom_oauth2_provider_config {
      client_id_wo                  = aws_cognito_user_pool_client.agent.id
      client_secret_wo              = aws_cognito_user_pool_client.agent.client_secret
      client_credentials_wo_version = 1

      oauth_discovery {
        discovery_url = local.discovery_url
      }
    }
  }
}
```

Alongside the customer's token, the runtime hands the container a workload
access token, an opaque token that identifies this agent, and the customer
it is acting for, to AgentCore Identity. The agent presents it and gets a
gateway token back. The secret read, the form post and the token cache
from post 02 collapse to one call:

```python
def access_token(workload_token):
    response = client().get_resource_oauth2_token(
        workloadIdentityToken=workload_token,
        resourceCredentialProviderName=os.environ["CREDENTIAL_PROVIDER"],
        scopes=[os.environ["TOKEN_SCOPE"]],
        oauth2Flow="M2M",
    )
    return response["accessToken"]
```

`M2M` is the `client_credentials` flow. The same call with
`USER_FEDERATION` is how an agent gets a token for a third party such as
Google or GitHub on the customer's behalf, with the consent step and the
per-customer token both handled by the vault. Brightwell's agent has no
third party to reach yet, so that stays a sentence.

The execution role needs two statements for this. The token call is scoped
to this provider and this runtime's workload identity, and the vault reads
the client secret in the caller's name, so the role also has to be allowed
to read that one secret:

```hcl
{
  Sid    = "GatewayTokenFromVault"
  Effect = "Allow"
  Action = ["bedrock-agentcore:GetResourceOauth2Token"]
  Resource = [
    aws_bedrockagentcore_oauth2_credential_provider.gateway.credential_provider_arn,
    "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:token-vault/default",
    "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:workload-identity-directory/default",
    "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:workload-identity-directory/default/workload-identity/${local.runtime_name}-*"
  ]
},
{
  Sid      = "ReadVaultedClientSecret"
  Effect   = "Allow"
  Action   = ["secretsmanager:GetSecretValue"]
  Resource = one(aws_bedrockagentcore_oauth2_credential_provider.gateway.client_secret_arn).secret_arn
}
```

> NOTE: leave the second statement out and the token call fails with an
> `AccessDeniedException` naming a secret under
> `bedrock-agentcore-identity!default/oauth2/`. The vault owns that secret
> and reads it with the runtime's role, so the role has to be allowed to.

## 4 - Running it

A customer account, with the password set out of band and never written
down:

```bash
aws cognito-idp admin-create-user \
  --user-pool-id "$POOL" --username c-1000 --message-action SUPPRESS
aws cognito-idp admin-set-user-password \
  --user-pool-id "$POOL" --username c-1000 --password "$PASSWORD" --permanent
```

The customer signs in and gets an access token whose `username` is their
customer id:

```bash
TOKEN=$(aws cognito-idp initiate-auth --client-id "$CLIENT_ID" \
  --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters USERNAME=c-1000,PASSWORD="$PASSWORD" \
  --query AuthenticationResult.AccessToken --output text)
```

With a JWT authorizer the runtime is called over HTTPS with that token
rather than through the SigV4-signed CLI, and the body no longer says who
is asking:

```bash
curl -s "$INVOKE_URL" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id: $SESSION" \
  -d '{"prompt": "list my orders"}'
```

```json
{"result": {"customer_id": "c-1000", "orders": [
  {"order_id": 1033, "placed_at": "2026-01-22", "items": 1, "total": 12.0, "status": "delivered", "carrier": "DPD", "eta": null},
  {"order_id": 1038, "placed_at": "2026-01-26", "items": 4, "total": 238.0, "status": "delivered", "carrier": "DPD", "eta": null},
  ...
  {"order_id": 1255, "placed_at": "2026-07-20", "items": 2, "total": 106.5, "status": "delivered", "carrier": "DPD", "eta": null}
]}}
```

Seven orders, all c-1000's, because the agent asked for c-1000's orders
and nothing in the request could have said otherwise. An order on someone
else's account gets nothing:

```bash
-d '{"prompt": "where is order 1014?"}'
# {"result": {"error": "order 1014 is not on your account"}}
```

And without a token the request never reaches the agent:

```
HTTP/2 401
www-authenticate: Bearer resource_metadata="https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/.../invocations/.well-known/oauth-protected-resource?qualifier=DEFAULT"

{"jsonrpc":"2.0","error":{"code":-32001,"message":"Missing Authentication Token"}}
```

> NOTE: the session id header is still required and still has to be at
> least 33 characters, exactly as with the CLI. `$INVOKE_URL` is the
> runtime ARN URL-encoded into the service endpoint, and the demo's
> Terraform emits it as an output.

## Conclusion

The agent now knows who it is acting for. The runtime validates the
customer's token, the agent takes the customer from claims it did not
have to trust, and every order lookup, memory read and memory write is
scoped to that customer. The agent's own credentials live in the token
vault and its code holds no secret, one Terraform resource, two IAM
statements and one API call.

That is the precondition for the next post, where a Bedrock model is
handed the tools this series has built, the order lookups, memory and the
sandbox, and asked a question nobody wrote code for. It will answer as
the customer this post identified, which is the only sensible way to let
a model choose.

References:

- https://github.com/levantar-ai/demos/tree/main/agentcore/05-identity
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-oauth.html
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/identity.html
- https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_oauth2_credential_provider
