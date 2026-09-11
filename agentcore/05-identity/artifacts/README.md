# Deployment artifacts — captured from a real run

Captured from a deploy and invoke cycle of this demo on 2026-09-11 (region
`us-east-1`, account `134570442530`), agent image tag `2e36c2d`, policy engine
in `ENFORCE`. This is the on-behalf-of design. The earlier token-relay design
and its reviews are kept as history at the end.

## What was deployed

The agent gets its token for the order service from AgentCore Identity, on
behalf of the customer, instead of relaying the customer's Cognito token.

- Cognito pool `us-east-1_…`, one public customers client, admin-only
  user creation. Unchanged. The runtime's inbound `CUSTOM_JWT` authorizer still
  validates the customer's Cognito access token.
- An explicit AgentCore Identity workload identity, `demos_agentcore_05_agent`,
  the name the agent presents. (The runtime also auto-created its own,
  `demos_agentcore_05_identity-…`; the explicit one is what the token
  call uses, see findings.)
- An AgentCore Identity OAuth2 credential provider, `demos_agentcore_05_obo`,
  created through Cloud Control (`AWS::BedrockAgentCore::OAuth2CredentialProvider`)
  with `OnBehalfOfTokenExchangeConfig { GrantType TOKEN_EXCHANGE,
  ActorTokenContent NONE }`, `CLIENT_SECRET_BASIC`, discovery pointed at the
  exchange service. ARN
  `arn:aws:bedrock-agentcore:us-east-1:…:token-vault/default/oauth2credentialprovider/demos_agentcore_05_obo`.
- The exchange service, the OBO target Cognito cannot be: an HTTP API at
  `https://kc5n0arhqc.execute-api.us-east-1.amazonaws.com` fronting one Lambda
  (`/token`, `/authorize`, `/.well-known/openid-configuration`,
  `/.well-known/jwks.json`), signing ES256 with a KMS `ECC_NIST_P256` key the
  Lambda role can only `Sign` with. Client secret in Secrets Manager.
- The gateway `demos-agentcore-05-identity-gw-…`, its `CUSTOM_JWT`
  authorizer now pointed at the exchange service's discovery URL with
  `allowed_audience = ["brightwell-orders"]`. It no longer trusts Cognito's
  issuer at all.
- Policy engine `demos_agentcore_05_orders` with the same `permit`
  (`own_orders_only`) and `forbid` guard (`deny_other_customers_orders`) on
  `principal.getTag("username") == context.input.customer_id`. Unchanged.
- Runtime `demos_agentcore_05_identity-…`, env `WORKLOAD_NAME`,
  `OBO_PROVIDER_NAME`, `ORDERS_SCOPE`; role gains `GetWorkloadAccessTokenForJWT`,
  `GetResourceOauth2Token`, and `GetSecretValue` on the provider's managed secret.

## The chain, end to end

`list my orders` as c-1000 through the runtime returned c-1000's seven orders
(1033, 1038, 1059, 1084, 1218, 1242, 1255), `HTTP 200`. Under the hood, in
order, each step verified by the ones after it:

1. The runtime validated the inbound Cognito access token.
2. The agent called `GetWorkloadAccessTokenForJWT(workloadName=
   demos_agentcore_05_agent, userToken=<the Cognito token>)`.
3. It called `GetResourceOauth2Token(oauth2Flow=ON_BEHALF_OF_TOKEN_EXCHANGE,
   resourceCredentialProviderName=demos_agentcore_05_obo, scopes=["orders/read"],
   workloadIdentityToken=<the workload access token>)`.
4. AgentCore Identity brokered RFC 8693 against the exchange service's `/token`
   with the customer's Cognito token as `subject_token` and the registered
   client's basic auth.
5. The exchange service validated that Cognito token and minted the token below.
6. The agent relayed the minted token to the gateway.
7. The gateway validated it against the exchange issuer and audience, Cedar
   permitted `username == customer_id`, the Lambda ran.

## The minted token

Minted directly from the exchange service with c-1000's Cognito token, to
inspect it. Response `{access_token, issued_token_type:
urn:ietf:params:oauth:token-type:access_token, token_type: Bearer, expires_in:
300, scope: orders/read}`.

```
header  {"alg": "ES256", "typ": "JWT", "kid": "emymRDGf8v466M6hq75KAmkU99TbImBeNM7I1oeCrSg"}
claims  iss      https://kc5n0arhqc.execute-api.us-east-1.amazonaws.com
        aud      brightwell-orders
        sub      d478b4f8-8081-70a9-259f-f35d390bdcaf   (the Cognito sub)
        username c-1000                                 (copied from the verified token)
        scope    orders/read
        act      {"client_id": "brightwell-orders-agent"} (the registered client, not a workload)
        exp-iat  300 seconds
```

Against the customer's Cognito token that is audience-scoped to one gateway,
five minutes instead of an hour, and never the customer's own token downstream.

## The security proofs

Against the gateway directly (`probe_gateway.py`), policy engine in `ENFORCE`:

- Minted token for c-1000, `customer_id=c-1000`: `allowed: 7 orders for c-1000`.
- Minted token for c-1000, `customer_id=c-1001`: `denied by the gateway: Tool
  Execution Denied: Tool call not allowed due to policy enforcement [Policy
  evaluation denied due to deny_other_customers_orders]`. The forbid wins on the
  minted token's `username`.
- The customer's RAW Cognito token at the gateway: `HTTP 403`. The gateway no
  longer trusts that issuer, so relaying the customer's token cannot work; the
  agent must go through AgentCore Identity's exchange.
- The minted token with its last character altered: `HTTP 403`. Signature
  verified against the exchange JWKS.

Against the exchange service's `/token`:

- Wrong client secret: `401 {"error": "invalid_client"}`. No client auth: the
  same. Uniform, no oracle.
- `grant_type=password`: `400 unsupported_grant_type`.
- An `alg=none` subject token: `400 invalid_grant, "subject token rejected"`.
- `scope=orders/admin`: `400 invalid_scope`. `audience=payments`:
  `400 invalid_target`. Request parameters cannot widen the token.

At the runtime: no `Authorization` header, `HTTP 401`.

## What the first live apply taught

Findings only a real apply could produce, all encoded in the config now.

- **The gateway fetches the discovery document at create time** and parses it
  as OpenID Connect, which requires `authorization_endpoint`. Without it:
  `Failed to fetch discovery document from … (Service: AgentCredentialProvider,
  Status Code: 400)`. The exchange service now advertises one, backed by a
  route that answers `unsupported_response_type`, this issuer performs token
  exchange only. The OBO credential provider had accepted the same document;
  the inbound authorizer is the strict one.
- **The Cedar policies race their dependencies.** The engine validates the
  action against the gateway target's tool schema, so the permit created
  before the target failed with `unrecognized action
  AgentCore::Action::"orders___list_orders"`. And a forbid validated before any
  permit exists is refused as `Overly Restrictive: Policy Engine will deny
  every request` (default deny plus a forbid denies everything). The permit
  depends on the target; the forbid on both. The original deploy had not hit
  this because the forbid was added in a later apply.
- **`GetResourceOauth2Token` reads the provider's managed client secret in the
  caller's context.** The runtime's first call failed with `Access denied when
  retrieving secret 'arn:aws:secretsmanager:…:secret:bedrock-agentcore-identity!default/oauth2/demos_agentcore_05_obo-…'
  … not authorized to perform: secretsmanager:GetSecretValue`. The runtime role
  now has that one action on that one secret.
- **An explicit workload identity works for the token call.** The runtime
  auto-creates its own with an undocumented suffix, which a resource cannot
  reference from its own env. `GetWorkloadAccessTokenForJWT` with the explicit
  `demos_agentcore_05_agent` succeeded, which is what let the chain reach the
  provider at all.
- **The Cloud Control provider came up first time**, and its ARN settled the
  form the IAM docs are inconsistent about: service `bedrock-agentcore`,
  `oauth2credentialprovider` unhyphenated. The runtime policy still wildcards
  `token-vault/default/*`, which could now be tightened to that exact ARN.
- **The first cold start exceeded 120 seconds**: `HTTP 424 Runtime
  initialization time exceeded`. The container was healthy on the next call;
  nothing to fix, a note for the runbook.

## External review (gpt-5.6-sol via the OpenAI API), 2026-09-10 to 11

Two rounds before the code went near AWS, because the exchange service is a
token issuer.

- **Design review**, on the spec. Verdict: not safe to build as specified, because
  with `actorTokenContent = NONE` the service authenticates a client secret and
  cannot truthfully mint an `act` claim naming the agent workload. Fixed: `act`
  names the registered client and is described as such. Also required and
  adopted: signing bound to the immutable KMS key ARN; strict JWT validation
  through a mature library with the algorithm pinned and `jku`/`x5u`/embedded
  keys/`crit` rejected; validate-before-replace, fail-safe JWKS caching;
  output lifetime `min(5 min, subject remaining)`; request parameters never
  choose audience, scope, key or claims; the RFC 8693 `issued_token_type`;
  honest framing that KMS prevents key export, not signing by a compromised
  process, so compromise of the service or its role is total issuer
  compromise. Its correction that the flow enum is `ON_BEHALF_OF` was itself
  wrong; the boto3 reference and the live call confirm
  `ON_BEHALF_OF_TOKEN_EXCHANGE`.
- **Code review**, on the actual handler. Headline: no forgery path, a caller
  cannot mint another customer's token without a Cognito-signed access token.
  Blocker fixed: the JWK must be bound to the immutable key ARN and the `Sign`
  response's `KeyId` verified. Should-fixes adopted: configuration validated at
  startup so a typo fails closed rather than becoming compromise; P-256 JWK
  coordinates fixed to 32 octets; strict NumericDate types and `iat <= exp`;
  form parsing with blank values kept and duplicates rejected; unsupported
  actor parameters rejected; structural checks before the secret is read;
  short-TTL secret cache; a `WWW-Authenticate` challenge. Not adopted for a
  demo, stated instead: baking a current-plus-retiring JWKS at deploy time for
  key rotation. The post must not claim KMS prevents forgery, that only
  AgentCore can call `/token`, that `jti` prevents replay, that `act`
  identifies the workload, that the token is scope-limited unless Cedar
  enforces scope, or that this is categorically safer than relaying the token.

The post is reviewed separately before publishing; see the bottom of this file.

## History: the token-relay design, 2026-09-08

The first published cut of this post relayed the customer's Cognito token to
the gateway and enforced the customer with the same Cedar policy. It was
deployed (image `f32c415`), verified live in `LOG_ONLY` then `ENFORCE` (c-1000
for c-1000 allowed, c-1000 for c-1001 denied, symmetric, no-token 401, ID token
refused at the JWT authorizer), and reviewed over five gpt-5.6 rounds plus two
follow-ups (a section on what it does not solve; AgentCore Identity added to
the main diagram). Its findings that still stand were carried into this design:
the Cedar boundary covers only the orders tool while memory and the sandbox
stay agent-scoped; `LOG_ONLY` is fail-open; the `forbid` guard keeps the
invariant against future additive permits; the IAM evaluate actions
(`AuthorizeAction`, `PartiallyAuthorizeActions`) do not support resource-level
scoping; the runtime and gateway trust policies are narrowed to `runtime/*`
and `gateway/*`.

It was taken down because a post titled around AgentCore Identity provisioned
no AgentCore Identity resource. Its inbound auth was real but was configuration
on other resources, and the outbound side had been removed. The consent-based
3LO alternative was rejected as unnatural for a first-party shop. On-behalf-of
was the pattern, and Cognito cannot be its exchange target, hence the exchange
service above, framed honestly as the teaching stand-in for a managed IdP.
