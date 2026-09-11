# Knowing who your agent is acting for, with AgentCore Identity

## TL;DR;

This post shows AgentCore Identity brokering an on-behalf-of exchange, from
the token a customer signed in with, through the runtime and the agent, to a
token for the order service that a second Cognito user pool mints, so the
gateway sees only the minted token and a Cedar policy refuses any call whose
customer differs from it. Cognito's token endpoint does not offer the
exchange grant, so the exchange follows the architecture of AWS's own
sample, a small token-exchange front door in front of a Cognito pool whose
triggers verify and mint. An audience, a confidential client, a five-minute
token and fail-closed triggers are added on top.

> SOURCE CODE - All code for this post is available at:
> https://github.com/levantar-ai/demos/tree/main/agentcore/05-identity

**The token exchange in this post is a teaching component, not
production-grade. It exists to show the AgentCore Identity integration. In
production the exchange is done by a managed IdP with a supported
on-behalf-of integration.**

## Longer version

This series is building one thing, the order support agent for Brightwell,
a small online retailer of outdoor kit that ships with DPD and Royal Mail.
Posts 01 to 04 gave it a runtime, a tool that looks orders up, memory and a
sandbox. None of them knew who was asking, and post 02 said so at the time,
that the gateway established a legitimate client was calling, not that it
was entitled to a particular order.

Closing that gap is the whole of this post, and it matters because
filtering in the agent's own code is not an authorisation boundary. The
tempting fix, giving the agent a
broad credential and filtering results in its own code, is the one AWS's
Well-Architected Agentic AI Lens tells you not to reach for.

> The traditional approach of granting the agent broad credentials and
> relying on application-level filtering (such as adding WHERE clauses to
> queries) creates a single point of failure. A more resilient design moves
> authorization enforcement out of the agent's application code and into the
> infrastructure layer wherever possible.

https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentsec03.html

AgentCore Identity has two halves. Inbound Auth validates the token a caller
presents to a runtime or a gateway. Outbound Auth gives the agent tokens for
the things it calls, through a workload identity, credential providers and a
token vault. Relaying the customer's Cognito token to the gateway uses only
the inbound half, and is a sound pattern for a first-party tool, but it
provisions no AgentCore Identity resource at all. This design uses both
halves. The agent asks AgentCore Identity for a token for the order service, on
behalf of the customer, and AgentCore Identity brokers an exchange of the
customer's inbound token for one that a second Cognito pool mints. That is
the on-behalf-of flow. It suits a background agent because, where the provider
has already established the delegation, no further interactive consent is
asked for on each downstream call. This demo's exchange applies a fixed
first-party policy and has no consent screen at all.

![The agent's order-service token, brokered by AgentCore Identity on the customer's behalf and minted by the exchange pool](architecture.png)

## 1 - Inbound, the runtime checks the customer

The Cognito pool from post 02 keeps a public client for customers, who sign
in with a password and get an access token. The runtime validates that token
before the agent sees the request, through AgentCore Identity's inbound auth,
which is the `CUSTOM_JWT` authorizer on the runtime.

```hcl
authorizer_configuration {
  custom_jwt_authorizer {
    discovery_url   = local.discovery_url
    allowed_clients = [aws_cognito_user_pool_client.customers.id]
  }
}
```

AWS describes configuring the runtime this way as implementing authentication
"using OAuth and JWT bearer tokens with AgentCore Identity", Inbound Auth
being its name for the half that validates callers.

> This section shows you how to implement authentication and authorization
> for your agent runtime using OAuth and JWT bearer tokens with AgentCore
> Identity. You'll learn how to set up Cognito user pools, configure your
> agent runtime for JWT authentication (Inbound Auth), and implement
> OAuth-based access to third-party resources (outbound Auth).

https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-oauth.html

The `Authorization` header is on the runtime's request header allowlist, so
the agent receives the validated token. It reads the `username` claim as the
customer, refuses anything that is not an access token, and never takes the
customer from the request body. This part is not where the post's subject
lives.

> NOTE: the runtime's authorizer is built to accept an end user's token, so in
> a real system the customer's own app, or a backend for it, would invoke the
> runtime carrying that token. This demo has the customer call the runtime
> directly, which changes nothing about the token or the checks and keeps
> the subject on the identity mechanism rather than the application wiring.

## 2 - On behalf of the customer, the agent's token comes from AgentCore Identity

Here is the change. The agent does not send the customer's Cognito token to
the gateway. It asks AgentCore Identity for a token for the order service,
and AgentCore Identity brokers the exchange on the customer's behalf, with
the exchange in the next section doing the minting. AWS's description of the
flow is exactly the property wanted.

> Amazon Bedrock AgentCore Identity supports On-Behalf-Of (OBO) token
> exchange, enabling agents and other workloads—such as MCP servers—to
> exchange an inbound user access token for a new, scoped access token that
> targets a downstream resource server. As the exchange converts a token
> issued for one audience directly into a token for a different downstream
> audience, your agents can access protected resources on behalf of
> authenticated users without triggering additional consent flows.

https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/on-behalf-of-token-exchange.html

Two calls do it. The first turns the customer's inbound token into a workload
access token, which represents the agent acting for that customer. The second
uses it to request the resource token, and AgentCore Identity brokers the
exchange with the credential provider.

```python
workload_token = client.get_workload_access_token_for_jwt(
    workloadName=os.environ["WORKLOAD_NAME"],
    userToken=inbound_jwt,
)["workloadAccessToken"]

result = client.get_resource_oauth2_token(
    workloadIdentityToken=workload_token,
    resourceCredentialProviderName=os.environ["OBO_PROVIDER_NAME"],
    scopes=[os.environ["ORDERS_SCOPE"]],
    oauth2Flow="ON_BEHALF_OF_TOKEN_EXCHANGE",
)
```

Three AgentCore Identity resources sit behind that. A workload identity for
the agent, declared explicitly so its name is known when the runtime is
created. A credential provider configured for on-behalf-of exchange, which
authenticates the exchange with a client credential. And the token vault,
which the provider lives under. The client credential itself ends up in
three places, a Secrets Manager secret AgentCore Identity manages for the
provider, a second Secrets Manager secret the exchange front door validates
against, and the Terraform state that generated it, which is a reason to
keep that state encrypted and tightly controlled.

```hcl
resource "aws_bedrockagentcore_workload_identity" "agent" {
  name = "demos_agentcore_05_agent"
}

resource "aws_cloudcontrolapi_resource" "obo_provider" {
  type_name = "AWS::BedrockAgentCore::OAuth2CredentialProvider"
  desired_state = jsonencode({
    Name                     = "demos_agentcore_05_obo"
    CredentialProviderVendor = "CustomOauth2"
    Oauth2ProviderConfigInput = {
      CustomOauth2ProviderConfig = {
        OauthDiscovery             = { DiscoveryUrl = "${local.exchange_issuer}/.well-known/openid-configuration" }
        ClientId                   = local.exchange_client_id
        ClientSecret               = random_password.exchange_client_secret.result
        ClientAuthenticationMethod = "CLIENT_SECRET_BASIC"
        OnBehalfOfTokenExchangeConfig = {
          GrantType                    = "TOKEN_EXCHANGE"
          TokenExchangeGrantTypeConfig = { ActorTokenContent = "NONE" }
        }
      }
    }
  })
}
```

> NOTE: the provider is created through Cloud Control rather than
> `aws_bedrockagentcore_oauth2_credential_provider`, because that resource in
> the AWS provider, as of 6.64, does not model
> `on_behalf_of_token_exchange_config`. The CloudFormation type does.

> NOTE: `GetResourceOauth2Token` reads the provider's client secret in the
> caller's context, so the runtime role needs `secretsmanager:GetSecretValue`
> on the secret AgentCore Identity manages for the provider, named
> `bedrock-agentcore-identity!default/oauth2/<provider>-…`. Without it the
> first call fails with an access-denied on that secret.

## 3 - The exchange, built the way AWS's sample builds it

On-behalf-of exchange is RFC 8693, and it needs an authorisation server that
implements that grant. Cognito's token endpoint does not. It accepts exactly
three grant types.

> Must be `authorization_code` or `refresh_token` or `client_credentials`.

https://docs.aws.amazon.com/cognito/latest/developerguide/token-endpoint.html

AWS publishes a sample that closes that gap without leaving Cognito,
`sample-cognito-oauth2-token-exchange`, and this post's exchange follows its
architecture. The sample puts a token-exchange endpoint on API Gateway and
Lambda, which authenticates the calling service with a client secret and
verifies the user's token against the pool that issued it, and delegates the
minting to a second Cognito user pool through that pool's custom
authentication flow. The pool's own Lambda triggers verify the user's token
again and add the user's identity to the token Cognito issues.

> This sample demonstrates how to implement RFC 8693 OAuth 2.0 Token
> Exchange using Amazon Cognito with a true delegation pattern. The solution
> enables services to act on behalf of users while maintaining distinct
> service identities and implementing the principle of least privilege.

https://github.com/aws-samples/sample-cognito-oauth2-token-exchange

That arrangement has two properties worth having. AWS manages the Cognito
pool's signing keys and publishes its discovery document and JWKS, rather
than the front door holding or using a signing key. And the endpoint cannot
make Cognito issue a token unless the pool's triggers accept the custom
authentication flow. It can only start that flow in the exchange pool as a
fixed service user, with the customer's token as the challenge answer, and
the pool's triggers decide whether Cognito issues anything and what it
says. A compromised endpoint still needs a valid customer token to get a
token out.

What is taken from the sample is that architecture, not its configuration,
and the differences are material. The sample rotates its exchanges across
24 service identities for throughput; this demo has one. It accepts an ID
token as a fallback subject; this demo accepts an access token only. Its
pre-token enrichment returns a plain token when the exchange metadata is
absent; this demo's triggers refuse. Its pool also has a second client with
password and refresh flows; this demo has one app client with
`ALLOW_CUSTOM_AUTH` as its sole explicit flow, and its pre-token trigger
separately refuses refresh-token generation.
And it fronts a REST API with a separate authorizer; this demo's front door
checks the client secret itself. The sample is the shape; the hardening is
this demo's.

Three things are then added on top, each of which the sample leaves to you.
An audience. The sample's exchanged token has no `aud`, because Cognito
access tokens do not include one by default, and its production guidance
says so.

> Restrict the token audience/resource (RFC 8693 `audience`/`resource`) so
> exchanged tokens cannot be replayed against other downstreams, and enforce
> fine-grained, per-user authorization at the resource (for example with
> Amazon Verified Permissions).

https://github.com/aws-samples/sample-cognito-oauth2-token-exchange#security-considerations

Cognito's pre-token trigger may add `aud` to an access token on one
condition, that its value is the app client of the session.

> You can add an `aud` claim to access tokens, but its value must match the
> app client ID of the current session.

https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-lambda-pre-token-generation.html

So the exchange pool has one app client per downstream, and the orders
client's id is the minted token's `aud`. A second downstream would get a
second client and tokens that name it. A confidential client. The sample's
admin client is public, so anyone who learned its id could run the custom
flow against Cognito directly and skip the endpoint. Here the client has a
secret, the front door computes `SECRET_HASH` from it, and of the workload
roles in this stack only the front door's may read the Secrets Manager copy;
the same secret is also in the Terraform state and readable by any principal
allowed to describe the app client, and those are inside the compromise
boundary. And five minutes, Cognito's minimum validity, in place of the
sample's hour.

The front door's own job is small. It is a narrow token-exchange endpoint
that implements the request AgentCore Identity sends, with RFC 8693's
parameters, and neither it nor the discovery document it serves claims
general RFC 8693 or OIDC conformance. It authenticates the caller with the
client secret AgentCore Identity's provider holds, refuses any parameter
outside that contract, verifies the customer's token itself so a bad one
never costs a Cognito flow, and runs `AdminInitiateAuth` and
`AdminRespondToAuthChallenge` with the customer's token as the answer and,
again, in the client metadata.

```python
started = cognito.admin_initiate_auth(
    UserPoolId=pool, ClientId=client, AuthFlow="CUSTOM_AUTH",
    AuthParameters={"USERNAME": user, "SECRET_HASH": secret_hash},
)
answered = cognito.admin_respond_to_auth_challenge(
    UserPoolId=pool, ClientId=client, ChallengeName="CUSTOM_CHALLENGE",
    Session=started["Session"],
    ChallengeResponses={"USERNAME": user, "ANSWER": subject_token, "SECRET_HASH": secret_hash},
    ClientMetadata={"subject_token": subject_token, "grant": TOKEN_EXCHANGE_GRANT},
)
```

One thing in that call is the sample's compromise, kept here and named.
The customer's token goes to Cognito twice, as the challenge answer, which
the verify trigger sees, and in the client metadata, which is the only
channel the pre-token trigger has. Cognito's API reference is explicit about
that field.

> When you use the ClientMetadata parameter, note that Amazon Cognito won't
> do the following: Store the ClientMetadata value. Validate the
> ClientMetadata value. Encrypt the ClientMetadata value. Don't send
> sensitive information in this parameter.

https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_AdminRespondToAuthChallenge.html

A bearer token is sensitive information, and this demo puts one there
because the sample does and because it keeps the demo to five functions.
The right shape for a real exchange is a single-use handle in the metadata,
with the verify trigger writing the verified claims to a short-lived
encrypted record under that handle and the pre-token trigger consuming it
once. That is a store and a few more lines, and it is the part of this
exchange not to copy as written.

The pool's four triggers do the rest, and every one of them fails closed.
`define` runs the state machine, one challenge, then tokens or failure.
`create` issues the challenge. `verify` validates the answer against the
customer pool, strictly, and refuses unless the answer is byte for byte the
token in the client metadata, which is the copy the last trigger reads, so
one customer's token cannot be answered with and another's minted for.
`pretoken` validates that copy again, because Cognito passes client metadata
through unvalidated, and then writes the claims.

```python
event["response"] = {
    "claimsAndScopeOverrideDetails": {
        "accessTokenGeneration": {
            "claimsToAddOrOverride": {
                "aud": client_id,
                "customer_id": claims["username"],
                "customer_sub": claims["sub"],
            },
            "scopesToAdd": [ORDERS_SCOPE],
            "scopesToSuppress": ["aws.cognito.signin.user.admin"],
        },
    },
}
```

Two claims Cognito will not let a trigger change are `sub` and `username`.
They stay the service user's, one fixed user that every exchange through
this front door runs as, so the token's subject is that service identity
and the customer travels as `customer_id`. That is the sample's "distinct
service identities" and the reverse of RFC 8693's `act` shape, where the
subject stays the user; the token carries no claim about which AgentCore
workload asked for it. Cedar reads a claim either way.

Be precise about what this does not buy. Whoever can change the triggers,
the pool, its app client or its service user controls what the exchange pool
mints. The front door's role can mint for any customer whose token it is
given, which is its job, and so can anyone holding the app client's secret,
which is in Secrets Manager and in the Terraform state. Once issued, the
minted token remains usable until its own five-minute expiry. Its lifetime
is not capped to the customer token's remaining lifetime, and customer
sign-out, disablement or revocation does not invalidate it. And the front door's discovery document is a shim that
tells AgentCore Identity where the token endpoint is, not an OIDC provider
document; the gateway uses the exchange pool's real one. A managed IdP with
a supported on-behalf-of integration is still the production answer; this
is the smallest teaching implementation used here, with the trust and replay
limits above.

## 4 - The gateway trusts the exchange pool, and Cedar still decides

The gateway's authorizer is pointed at the exchange pool's own discovery
document, a genuine Cognito one, rather than at the customer pool. The
customer's access token has no `aud`, whereas the minted token carries the
orders client as `aud`, so the gateway validates by `allowed_audience`.

```hcl
authorizer_configuration {
  custom_jwt_authorizer {
    discovery_url    = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.exchange.id}/.well-known/openid-configuration"
    allowed_audience = [aws_cognito_user_pool_client.orders.id]
  }
}
```

That has a consequence worth stating plainly. The gateway is configured for
the exchange pool and that audience, so the customer's own token is not
accepted at the gateway at all, and relaying it is not a weaker option the
agent might fall back to, it does not work. Be equally plain about the
converse. The gateway accepts any correctly signed token from the exchange
pool with that audience and cannot tell whether AgentCore Identity brokered
it. The normal agent path obtains it through AgentCore Identity, but the
front door is also callable directly by anyone holding the provider's client
secret and a valid customer token, and the runtime role can read that
secret, because `GetResourceOauth2Token` reads it in the caller's context. A
direct caller still needs a customer's valid token to be issued that
customer's `customer_id`, so this does not let one customer become another.

> NOTE: for this flow, AgentCore Identity's credential provider uses the
> front door's discovery URL to locate `/token`, and the exchange pool's own
> document points `token_endpoint` at Cognito's, which does not offer the
> grant. So the front door serves a small document of its own for the
> provider, with `token_endpoint` pointing at itself and `jwks_uri` at the
> exchange pool, and the live run shows the provider calling that endpoint.
> It is a compatibility shim, not an OIDC provider document. The gateway
> does not use it; it validates the minted token against the exchange
> pool's Cognito discovery document.

Per-customer enforcement is the Policy in AgentCore engine from the first
version, unchanged, evaluating a Cedar policy on every tool call.

> For every tool invocation, the policy engine evaluates all applicable
> policies against the request to determine whether to allow or deny access.
> The engine enforces default-deny and forbid-wins semantics automatically.

> When a AgentCore Gateway uses OAuth authorization, the principal is
> created from the JWT token's `sub` claim. OAuth principals support tags
> that contain JWT claims such as username, scope, role, etc.

https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-core-concepts.html

Every claim in the minted token becomes a principal tag, and the rule is the
one line it always was, now on `customer_id`. The principal itself is the
token's `sub`, the exchange pool's service user; the customer is the tag.

```hcl
permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"orders___list_orders",
  resource == AgentCore::Gateway::"${aws_bedrockagentcore_gateway.orders.gateway_arn}"
) when {
  principal.hasTag("customer_id") &&
  principal.getTag("customer_id") == context.input.customer_id
};
```

A matching `forbid` guards it, so a broad permit added in a later post cannot
widen it, forbid winning over any permit.

> NOTE: the engine validates a policy's action against the gateway target's
> tool schema, so the permit must be created after the target, and a forbid
> validated before any permit exists is refused as overly restrictive, so it
> must be created after the permit. Both are `depends_on` in the config.

## 5 - Running it

The whole path. The runtime validates the customer's Cognito token, the
exchange front door and then the exchange pool's triggers validate it again
during the exchange, and the gateway validates the minted token before Cedar
evaluates the call.

![The customer's token validated at the runtime, exchanged on their behalf, and checked by Cedar at the gateway](sequence.png)

A customer signs in and calls the agent, and the happy path looks like every
earlier post, because the exchange happens inside it.

```bash
$ curl "$INVOKE_URL" -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -H "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id: $SESSION" \
    -d '{"prompt": "list my orders"}'
{"result": {"customer_id": "c-1000", "orders": [{"order_id": 1033, ...}, ...]}}
```

The token that reached the gateway is worth looking at. Exchanging c-1000's
Cognito token at the front door directly, to inspect the result, gives this.

<!-- cspell:ignore aietapviq -->
```
header  {"alg": "RS256", "kid": "TvIiDULuRXM0iy7NC3MrMWzCRlgDWZDO6+WYHscJp4U="}
claims  iss         https://cognito-idp.us-east-1.amazonaws.com/us-east-1_xM9xiUfea
        sub         74386448-1081-7039-67b7-010085d46183
        username    orders-agent
        client_id   5ujh25q6q73kqq2u1aietapviq
        aud         5ujh25q6q73kqq2u1aietapviq
        customer_id c-1000
        customer_sub d478b4f8-8081-70a9-259f-f35d390bdcaf
        scope       orders/read
        token_use   access
        exp-iat     300 seconds
```

Signed by the exchange pool with Cognito's own key. Compared with relaying
the customer's token, this one carries the orders client as its audience,
which the gateway is configured for, expires after five minutes, names the
exchange pool's fixed service user as its subject and the customer as
`customer_id`, and the customer's credential itself never reaches the
gateway or the tool. The front door's log shows what AgentCore Identity
sends. It is `grant_type`, `subject_token`, `subject_token_type` and
`scope`, with no `audience` or `resource`, so the audience is the exchange's
decision, not the caller's.

The interesting calls are the ones that should not work, made against the
gateway directly with that minted token.

```bash
$ TOKEN="$MINTED" python3 probe_gateway.py c-1000
allowed: 7 orders for c-1000

$ TOKEN="$MINTED" python3 probe_gateway.py c-1001
denied by the gateway: Tool Execution Denied: Tool call not allowed due to
policy enforcement [Policy evaluation denied due to deny_other_customers_orders]

$ TOKEN="$COGNITO" python3 probe_gateway.py c-1000
error (not a policy decision) for c-1000: Client error '403 Forbidden'
```

The second is Cedar refusing another customer's orders on the minted token's
`customer_id`, before the tool runs. The third is the customer's raw Cognito
token being refused outright, the gateway does not trust the customer pool.
A token with a signature character altered, or with `customer_id` edited to
c-1001 under the original signature, gets the same 403. At the front door a
wrong client secret, a widened scope, a different audience or an unsigned
subject token are each refused before anything reaches the exchange pool.
And at the exchange pool itself, with the front door bypassed, custom auth
without the client secret is refused, password and SRP flows are refused, a
bogus answer is refused, a valid answer with a different token in the client
metadata is refused, and a valid answer with no metadata is refused. The
refresh and ID-token probes identify two controls that matter. Cognito processed a
`REFRESH_TOKEN_AUTH` attempt on the orders client even though its only
enabled flow is custom auth, and it was the pre-token trigger's refusal
that stopped a token coming out, so the trigger is the control there, not
the client's flow list. And the gateway's authorizer accepted the exchange
pool's ID token, because its `aud` is the same app client. The policy
evaluation reported the `forbid`, an ID token having no `customer_id`; the
permit would not have applied either, so default deny would have refused
it, and the forbid's real purpose is to keep that invariant against a
broader permit added later.

## 6 - What limits the token's use at another service

The runtime's network is public, so the agent can send a request anywhere.
The question a security review asks is what the agent holds that another
service would accept, and the answer is that the minted token is accepted
by any verifier configured to trust the exchange pool and the orders
client's audience, which in this demo is the order gateway alone, subject to
Cedar. It is worth walking the reasons, because each is a different control
and none of them is the agent's code.

The token names its audience, and the order gateway is the only downstream
in this demo configured to accept it. The exchange pool's pre-token trigger
writes the orders client's id as `aud`, and the gateway's JWT authorizer is
configured with that exact audience against the exchange pool's discovery
document, as section 4 showed. Isolation between downstreams is a distinct
app client per service and every verifier enforcing its own audience; a
payments gateway configured for a second client refuses this token before
any policy runs. That is the audience restriction the AWS sample's guidance
asks for. It limits
where the minted token can be replayed once it leaves the agent. The Cognito
access token has no `aud`, so a resource trusting the same pool and app
client has no audience check with which to tell a token meant for it from
one meant for something else. It does not shrink what a compromised agent
here could attempt, because the agent also holds the Cognito token.

The agent cannot ask for a different audience. The front door fixes the
audience and the scope in its configuration and refuses a request that names
any other, `invalid_target` and `invalid_scope`, which the tests cover and
the live probes confirmed. Nothing the agent puts in the request widens what
comes back.

Nobody can mint without the exchange pool's triggers. The front door holds
no key. The exchange pool's app client is confidential, so the custom flow
cannot be run against Cognito without its secret. Among the deployed
execution roles only the front door can read the Secrets Manager copy,
although Terraform state operators and principals allowed to describe the
app client can also obtain it. Even with that secret, the triggers refuse
anything that is not a valid customer token presented the same way twice.

Through AgentCore Identity, the runtime role can use only this one
provider. Its `GetResourceOauth2Token` is allowed on the exact ARN of the
`demos_agentcore_05_obo` credential provider and the one workload identity,
nothing else in the token vault. If the account held a second provider for a
payments issuer, this agent's role could not obtain a token from it. That
boundary is IAM, and it holds whatever the agent's code does.

There is no route to the order service that bypasses the gateway. The
runtime role has no `lambda:InvokeFunction`; only the gateway's role may
invoke the orders Lambda. The agent's only path to an order is through the
authorizer and then Cedar.

The gateway and the order tool do not accept the customer's Cognito token
as their bearer credential. The gateway does not trust the customer pool, so
relaying it is refused outright, as the probe in section 5 shows. The
runtime validates that token for invocation, and the exchange accepts it as
the subject token when the client also authenticates; no protected
downstream resource in this stack accepts it directly. The agent does hold
it, because the runtime forwards it, so anything outside this stack that
trusts the customer pool and app client would accept it. The design's answer
is that no downstream resource should, only the exchange.

And the minted token lives for five minutes. A token that leaks is usable
for that long, at any verifier configured to trust this pool and audience,
which in this demo is the order gateway.

Be equally precise about what this does not buy. Cedar prevents a
model-chosen or accidental `customer_id` from mismatching the token that was
presented. It does not prove the agent used the current invocation's token.
Cedar binds `customer_id` to the claim in whichever valid minted token
arrives, so a compromised agent serving many customers could reuse another
customer's token it had seen earlier and be permitted for that customer. It
cannot invent a customer it holds no valid token for. Stronger isolation
means performing the exchange in a trusted per-request component outside
the agent's code, or isolating workloads per tenant. It is still a bearer
token, so a stolen minted token is usable until it expires, and a stolen
Cognito token can still call the runtime and cause fresh exchanges until it
expires. The `scope` claim is carried, not enforced, because the Cedar
policy checks the customer and not the scope; the audience is what the
gateway enforces. And Cedar constrains the call, not the rows. It refuses a
`list_orders` whose requested customer differs from the token, but it cannot
see what the Lambda returns, so the order service must still select only
that customer's rows. Here it does, and a test proves it, but that is code
again, and where the data layer can enforce the tenant key it should.

For the orders tool the design implements the Well-Architected lens on tool
authorisation, the gateway and its policy engine authorising every invocation
against a declarative policy before the Lambda runs, and it propagates the
customer's identity to that enforcement point as claims in a token minted for
the purpose rather than giving the agent broad access.

https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentsec02.html

## Conclusion

The agent now acts for a known customer with a token brokered by AgentCore
Identity and minted for the purpose by a Cognito pool, with Cognito's keys,
the way AWS's own sample does it. Inbound auth establishes who the customer
is, the on-behalf-of exchange gives the agent a token for the order service
that is audience-restricted, five minutes long and not the customer's own
credential, carrying an `orders/read` scope claim this demo does not
enforce, and Policy in AgentCore refuses a call for anyone but the customer
named in that token before the tool runs. The gateway accepts no static
agent credential, the customer's token is refused there even if relayed by
mistake, and nothing mints without the exchange pool's triggers. What is not
bound is the token to the invocation; a compromised agent serving many
customers could present another customer's still-valid token and be
permitted for them. The memory and sandbox paths are still isolated in the
agent's own code, so moving those behind the same gateway and policy is how
you would finish the job, and in production the exchange belongs to a
managed IdP with a supported on-behalf-of integration rather than a pool
and a front door you run.

That is the precondition for the next post, where a model is handed the
tools this series has built and chooses the arguments, including the
customer id. Provided the model chooses the argument and not the token, which
trusted code supplies, a wrong choice is refused at the gateway rather than
read from someone else's account.

References:

- https://github.com/levantar-ai/demos/tree/main/agentcore/05-identity
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/on-behalf-of-token-exchange.html
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-oauth.html
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-core-concepts.html
- https://docs.aws.amazon.com/cognito/latest/developerguide/token-endpoint.html
- https://github.com/aws-samples/sample-cognito-oauth2-token-exchange
- https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-lambda-pre-token-generation.html
- https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentsec02.html
- https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentsec03.html
- https://datatracker.ietf.org/doc/html/rfc8693
