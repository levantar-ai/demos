# Deployment artifacts — captured from a real run

Captured from a deploy and invoke cycle of this demo on 2026-09-11 (region
`us-east-1`, account `134570442530`), first on agent image tag `2e36c2d` and
finally, after the review rounds below, on `f989799` (the committed code), with
the policy engine in `ENFORCE`. The chain, the minted token and every probe
were re-run on that final image and matched. This is the on-behalf-of design.
The earlier token-relay design and its reviews are kept as history at the end.

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
  Lambda role can `Sign` and `GetPublicKey` with but not administer. Client
  secret in Secrets Manager.
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
  same. Missing and incorrect client authentication return the same response;
  the endpoint is still an online check of the secret, mitigated by its
  entropy and the stage throttle, not removed.
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
  `oauth2credentialprovider` unhyphenated. The runtime policy was then
  tightened to the exact provider and workload-identity ARNs, and the managed
  secret to its exact ARN read from the Cloud Control resource's `properties`
  (`ClientSecretArn.SecretArn`), and the chain re-verified on 2026-09-11.
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

### Post review rounds, 2026-09-11

The post, runbook, agent and Terraform were reviewed together after the live
run, with the same reviewer.

- **Round 1**, 18 findings, all applied but one (the aws-vault profile in the
  runbook is the repo's convention).
- **Round 2**, verdict not ready. Two blockers, both accepted: the TL;DR and
  conclusion had drifted back to an end-to-end binding claim that section 6
  itself denies, so both now state the bounded property (Cedar refuses a
  mismatched customer against the presented token; it cannot bind that token
  to the current invocation; a compromised shared agent could replay another
  customer's still-valid token; the next-post claim holds only while the model
  chooses the argument and not the token). And Cedar constrains the call, not
  the rows, so the order Lambda's own filtering is now stated as a
  responsibility and tested (`agent/test_tenancy.py`, alongside the memory
  namespace tests the reviewer asked for). Should-fixes applied: the runtime
  role reads the provider's managed secret by exact ARN rather than a prefix
  wildcard; the JWKS cache now has a six-hour maximum stale age after which
  subject tokens are refused until a refresh succeeds, with tests; "never
  presents the credential downstream" narrowed to "only to AgentCore Identity
  and the exchange issuer, never to the gateway or tool"; "scoped" replaced by
  "audience-restricted" wherever only the audience is enforced; "holds no
  static credential" replaced by "the gateway accepts no static agent
  credential" because the runtime can read the provider's client secret; the
  runbook warning names the bearer token as well as the client secret; the
  code comment on consent made provider-specific; trusted identity propagation
  limited to the services that support it; four stale Terraform comments from
  the relay design rewritten. Not adopted: a `getpass` helper for the runbook
  probes, an isolated demo account with synthetic data is the stated
  condition instead.
- **Round 3**, with the order tool and memory code in the material, no
  blockers, ten should-fix and minor items, all applied: the same row-level
  overclaim in three code docstrings; the diagrams' "caller's username" and
  "caller's own orders" labels, which restated the binding the prose had
  dropped, now "token username" and "matching customer_id: permit the call",
  and "up to 5 min" for the lifetime; "nothing in the request can change the
  claims" narrowed to "no other request parameter", since the subject token is
  itself in the request; the `AssumeRoleWithWebIdentity` alternative now says
  federation enforces nothing without a trust policy and a partition-key
  condition; the discovery document named as a compatibility shim advertising
  capabilities the issuer does not implement; a broken comment in cognito.tf;
  the runtime's auto-created workload identity output renamed so it is not
  mistaken for the one the chain uses; the KMS permissions stated correctly
  in this record.
- **Round 4**, one blocker and four should-fix or minor, all applied: the
  TL;DR had said the credential goes "only" to AgentCore Identity and the
  issuer, omitting that the runtime forwards it to the agent container first,
  so it now traces the path from the runtime; the federation alternative now
  says it needs a token made for federation (a Cognito ID token, not this
  post's access token, which has no `aud`) and a role that pins the partition
  key; "identity is where agent security is won or lost" replaced with the
  concrete point; the exchange role's KMS policy split into a `Sign` statement
  conditioned on `ECDSA_SHA_256` and a plain `GetPublicKey` statement, rather
  than one statement relying on `ForAllValues` passing when the key is absent,
  applied live and the JWKS, mint and probes re-run; two "scoped" comments
  made "audience-restricted".
- **Round 5**, five should-fix or minor, all applied: the TL;DR now traces
  every hop (runtime to agent, agent to AgentCore Identity, AgentCore Identity
  to the issuer; the gateway sees the minted token, the tool the permitted
  arguments); Entra named as AgentCore Identity's provider-specific
  on-behalf-of integration rather than an RFC 8693 issuer, and Auth0 dropped;
  the federation alternative reduced to the one path described accurately
  (user pool as IAM OIDC provider, ID token, app-client audience,
  `dynamodb:LeadingKeys`); an explicit anti-impersonation test submitting
  `username`, `sub`, `aud` and `exp` form parameters against a valid subject
  token; the identity.py comment naming the explicit workload identity.
- **Round 6**, one should-fix: the handler docstring and exchange.tf header
  still named Entra and Auth0 as what the service stands in for. Replaced
  with "a managed IdP with a supported on-behalf-of integration".
- **Round 7**, round 6 confirmed resolved; two further items applied: the
  gateway role's two evaluation actions on `*` are account-wide, and scoping
  the engine's read actions does not narrow what they can evaluate, said so
  in the runbook and the Terraform comment; "no oracle" for the `/token`
  client-auth failures replaced with the accurate statement.
- **Round 8**, "No material findings remain. Verdict: ready to publish."
- **Rounds 9 to 11**, after Andy asked for two changes post-publication:
  reference AWS's `sample-cognito-oauth2-token-exchange` (the same
  exchange-endpoint pattern, delegating the minting to a second Cognito pool,
  and whose production guidance asks for the audience restriction this demo
  applies), and replace the alternatives paragraph with an explanation of
  why the design does not let the agent into another service. Round 9 found
  the first draft of that section claimed too much (the audience restriction
  framed as what makes the token "safer" than the Cognito token; "the agent
  can only reach this one provider" read as a network boundary when the
  runtime is public; "nothing else in this stack trusts the pool" when the
  runtime and the exchange both validate it; "AWS's own answer" for a
  sample). All reframed to authorisation: the minted token authorises calls
  to the order gateway alone, the audience limits replay once the token
  leaves the agent, IAM limits which provider AgentCore Identity will serve
  the role, no `lambda:InvokeFunction` on the runtime role, and the Cognito
  token is accepted by nothing downstream as a bearer credential. Round 10
  caught an `authorizer_config` typo in the copied snippet, the README and
  policy.tf comments restating the invocation binding, and the diagrams'
  `aud = orders` shorthand. Round 11: "No material findings remain. Verdict:
  ready to publish."

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
