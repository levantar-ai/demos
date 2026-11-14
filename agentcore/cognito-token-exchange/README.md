# Cognito's own token exchange behind AgentCore Identity

The live test behind the insight
[Cognito now does the token exchange we had to build](https://levantar.ai/insights/cognito-token-exchange.html).
On 12 November 2026 AWS added OAuth 2.0 token exchange, RFC 8693, to Amazon
Cognito. This runs it behind AgentCore Identity's on-behalf-of flow in place of
the front door, exchange pool and triggers that
[post 05](../05-identity/) had to build.

## What it does

`run.py` builds a scratch stack in us-east-1, runs the exchange through
AgentCore Identity in impersonation and delegation, shows three requests that
fail, and deletes everything in a `finally` block, exiting non-zero and naming
anything it could not delete. Nothing is written to disk, and pool, client and
customer ids are redacted in what it prints.

It creates a Cognito pool on the Essentials plan, a managed login version 2
domain, an `orders` resource server, a customer app client, an agent app client
with the two new flows `ALLOW_TOKEN_EXCHANGE_IMPERSONATION` and
`ALLOW_TOKEN_EXCHANGE_DELEGATION`, one test customer, a workload identity and
two on-behalf-of credential providers, `NONE` and `M2M` actor token content.

```bash
pip install -r requirements.txt
aws-vault exec <profile> -- python3 run.py
```

The account needs Cognito token exchange enabled, and the caller needs to be
able to create and delete Cognito pools and AgentCore workload identities and
credential providers. A run takes a couple of minutes, most of it waiting for
the new domain to resolve.

## What it showed

The output of the last run is in [artifacts/run.txt](artifacts/run.txt).

- Both modes return a token Cognito signed for the customer, `aud` `orders`.
  Delegation adds an `act` claim naming the agent's app client.
- AgentCore Identity's exchange fails with HTTP 400 unless
  `customParameters` sets `subject_token_type` to the access token type.
  Cognito refuses the generic JWT type.
- Asking for `orders/read`, a scope the customer's token does not hold, is
  refused. The agent asks for no scopes, which the service accepts although
  the API reference wants at least one.
- Each exchanged token lived about an hour and expired no later than the
  customer's own token.

## The managed login domain

`run.py` creates the domain on managed login version 2 because the first test,
on 13 November 2026, did not. With a domain created without it, every exchange
at the token endpoint returned
`{"error":"invalid_request","error_description":"token_exchange_requires_managed_login"}`.
Updating that domain to version 2 had not taken effect after five minutes, and
deleting and recreating it on version 2 worked on the next call. The AWS guide
asks only for a domain, so this may change.

## What it does not test

It calls AgentCore Identity directly with the customer's token, as the agent
does, rather than from a deployed agent on AgentCore Runtime. The gateway,
Cedar and the orders Lambda are not run against the exchanged token. The
gateway's authorizer would trust the customer pool with `orders` as the
audience, and Cedar would compare `username` with the tool's `customer_id`
argument.

## Why boto3 and not Terraform

The Terraform AWS provider, at 6.73.0, rejects the two new client flows, as its
[validation list](https://github.com/hashicorp/terraform-provider-aws/blob/v6.73.0/internal/service/cognitoidp/user_pool_client.go)
comes from an SDK enum without them, so the stack is built with boto3. boto3
1.44.3 passes them through but its
[service model](https://github.com/boto/botocore/blob/1.44.3/botocore/data/cognito-idp/2016-04-18/service-2.json)
has no `GetDerivedToken`, so this uses the token endpoint, which is what
AgentCore Identity calls.

## The diagram

[removed.png](removed.png) is post 05's published architecture with the part
Cognito's exchange removes, the front door and the exchange pool, marked in
red. `highlight.py` draws it over
[post 05's architecture.png](../05-identity/architecture.png), which it reads
unchanged.
