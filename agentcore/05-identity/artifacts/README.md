# Deployment artifacts — captured from a real run

<!-- cspell:ignore adpy Ufea icwpdqo stgk aietapviq -->

Captured from deploy and invoke cycles of this demo on 2026-09-11 (region
`us-east-1`, account `134570442530`), policy engine in `ENFORCE`. The final
design is the on-behalf-of exchange built on AWS's
`sample-cognito-oauth2-token-exchange`: a front door and a second Cognito
pool that mints. Two earlier designs, the KMS-signed issuer that this
replaced the same day and the token-relay design of 2026-09-08, are kept as
history at the end with their reviews.

## What was deployed

The agent gets its token for the order service from AgentCore Identity, on
behalf of the customer, instead of relaying the customer's Cognito token.

- Customer pool `us-east-1_RVnT3adpy`, one public customers client, admin-only
  user creation. Unchanged. The runtime's inbound `CUSTOM_JWT` authorizer
  validates the customer's Cognito access token.
- An explicit AgentCore Identity workload identity, `demos_agentcore_05_agent`.
- An AgentCore Identity OAuth2 credential provider, `demos_agentcore_05_obo`,
  created through Cloud Control (`AWS::BedrockAgentCore::OAuth2CredentialProvider`)
  with `OnBehalfOfTokenExchangeConfig { GrantType TOKEN_EXCHANGE,
  ActorTokenContent NONE }`, `CLIENT_SECRET_BASIC`, discovery pointed at the
  front door. Unchanged across the three designs.
- The exchange. The front door, an HTTP API at
  `https://kc5n0arhqc.execute-api.us-east-1.amazonaws.com` fronting one Lambda
  (`/token`, `/authorize`, `/.well-known/openid-configuration`), which holds no
  key. The exchange pool `us-east-1_xM9xiUfea` (`ESSENTIALS` tier), its
  confidential app client `orders` (`5ujh25q6q73kqq2u1aietapviq`,
  `ALLOW_CUSTOM_AUTH` only, 5-minute access and ID tokens, 60-minute refresh),
  its service user `orders-agent` (`CONFIRMED`), and four trigger Lambdas
  (`define`, `create`, `verify`, `pretoken` at `V2_0`). Two Secrets Manager
  secrets (the front door's client secret; the app client's secret, read only
  by the front door's role) and one SSM parameter with the pool, client and
  user ids, read by all five functions.
- The gateway `demos-agentcore-05-identity-gw-icwpdqo778`, its `CUSTOM_JWT`
  authorizer pointed at the exchange pool's own discovery document with
  `allowed_audience = [<orders client id>]`. It does not trust the customer
  pool.
- Policy engine `demos_agentcore_05_orders` with the `permit`
  (`own_orders_only`) and `forbid` guard (`deny_other_customers_orders`) on
  `principal.hasTag("customer_id") && principal.getTag("customer_id") ==
  context.input.customer_id`.
- Runtime `demos_agentcore_05_identity-w4stgk82ss` on image `f989799`, env
  `WORKLOAD_NAME`, `OBO_PROVIDER_NAME`, `ORDERS_SCOPE`; role scoped to the
  exact workload identity, provider and managed-secret ARNs.

The apply of the exchange pool was 23 added, 5 changed, 6 destroyed, first
time, after importing the front door's pre-existing log group into state.

## The chain, end to end

`list my orders` as c-1000 through the runtime returned c-1000's seven orders,
`HTTP 200`; `where is order 1033` returned the order. In order, each step
verified by the ones after it:

1. The runtime validated the inbound Cognito access token.
2. The agent called `GetWorkloadAccessTokenForJWT(workloadName=
   demos_agentcore_05_agent, userToken=<the Cognito token>)`.
3. It called `GetResourceOauth2Token(oauth2Flow=ON_BEHALF_OF_TOKEN_EXCHANGE,
   resourceCredentialProviderName=demos_agentcore_05_obo, scopes=["orders/read"],
   workloadIdentityToken=<the workload access token>)`.
4. AgentCore Identity called the front door's `/token` with the registered
   client's basic auth and, per the front door's log of field names,
   `grant_type`, `subject_token`, `subject_token_type` and `scope`; no
   `audience` or `resource`.
5. The front door authenticated the client, checked the request, validated
   the customer's token, then ran `AdminInitiateAuth(CUSTOM_AUTH)` and
   `AdminRespondToAuthChallenge` in the exchange pool as `orders-agent`, with
   `SECRET_HASH`, the customer's token as `ANSWER` and again in
   `ClientMetadata`.
6. The pool's `define`, `create`, `verify` (answer == metadata copy, then
   validated) and `pretoken` (validated again, claims written) triggers ran,
   and Cognito minted the token below.
7. The agent relayed it to the gateway, which validated it against the
   exchange pool and audience; Cedar permitted `customer_id` == the claim; the
   Lambda ran.

## The minted token

Minted directly from the front door with c-1000's Cognito token, to inspect
it. Response `{access_token, issued_token_type:
urn:ietf:params:oauth:token-type:access_token, token_type: Bearer, expires_in:
300, scope: orders/read}`; the ID and refresh tokens Cognito returned were
dropped.

<!-- cspell:ignore aietapviq -->
```
header  {"alg": "RS256", "kid": "TvIiDULuRXM0iy7NC3MrMWzCRlgDWZDO6+WYHscJp4U="}
claims  iss          https://cognito-idp.us-east-1.amazonaws.com/us-east-1_xM9xiUfea
        sub          74386448-1081-7039-67b7-010085d46183   (the service user, reserved)
        username     orders-agent                            (reserved)
        client_id    5ujh25q6q73kqq2u1aietapviq              (the orders app client, reserved)
        aud          5ujh25q6q73kqq2u1aietapviq              (added by pretoken; Cognito allows only the session's client)
        customer_id  c-1000                                  (added, from the verified token's username)
        customer_sub d478b4f8-8081-70a9-259f-f35d390bdcaf   (added, from its sub)
        scope        orders/read                             (scopesToAdd; aws.cognito.signin.user.admin suppressed)
        token_use    access
        exp-iat      300 seconds
```

## The security proofs

Against the gateway directly (`probe_gateway.py`), policy engine in `ENFORCE`:

- Minted token, `customer_id=c-1000`: `allowed: 7 orders for c-1000`.
- Minted token, `customer_id=c-1001`: `denied by the gateway … [Policy
  evaluation denied due to deny_other_customers_orders]`.
- The customer's RAW Cognito token: `HTTP 403`. The gateway does not trust
  the customer pool.
- The minted token with a signature character flipped mid-segment: `403`.
  With `customer_id` edited to c-1001 under the original signature: `403`.
- The minted token five minutes later: `403`.
- The exchange pool's ID token (obtainable only with the app client's
  secret): accepted by the authorizer, since its `aud` is the same client,
  and denied by the `forbid`, since it has no `customer_id`. The authorizer
  does not check `token_use`; the forbid guard does that work.

Against the front door's `/token`:

- Wrong client secret: `401 {"error": "invalid_client"}`. No client auth: the
  same. Missing and incorrect client authentication return the same response;
  the endpoint is still an online check of the secret, mitigated by its
  entropy and the stage throttle, not removed.
- `grant_type=password`: `400 unsupported_grant_type`. Any parameter outside
  the RFC 8693 set (`username=c-1001`, say): `400 invalid_request, unknown
  parameter`.
- An `alg=none` subject token: `400 invalid_grant`.
- `scope=orders/admin`: `400 invalid_scope`. `audience=payments`:
  `400 invalid_target`. `audience=<the orders client id>`: accepted.

Against the exchange pool with the front door bypassed:

- `InitiateAuth CUSTOM_AUTH` without `SECRET_HASH`: `NotAuthorizedException`.
- `USER_PASSWORD_AUTH`: `NotAuthorizedException`. `ADMIN_USER_PASSWORD_AUTH`
  and `USER_SRP_AUTH` with a correct `SECRET_HASH`: `InvalidParameterException`
  (flow not enabled).
- With the app client's secret: bogus `ANSWER` → `NotAuthorizedException`;
  valid `ANSWER` but a different `subject_token` in `ClientMetadata` →
  `NotAuthorizedException`; valid `ANSWER`, no metadata →
  `NotAuthorizedException`; valid `ANSWER` with the matching copy → a token
  for c-1000, 299 s, plus an ID and a refresh token. That last path is the
  front door's own privilege, and holders of that secret (it is also in the
  Terraform state) have it.
- `REFRESH_TOKEN_AUTH` with that refresh token, minutes after issue, on both
  `InitiateAuth` and `AdminInitiateAuth`: `UserLambdaValidationException`.
  Cognito processed the refresh on a client whose only flow is
  `ALLOW_CUSTOM_AUTH`; the `pretoken` log shows `Refused: not an exchange`.
  The trigger is the control, not the client's flow list.

At the runtime: no `Authorization` header, `HTTP 401`.

## What the live applies taught

- **Terraform's `aws_cognito_user.password` is permanent.** The design
  review expected `FORCE_CHANGE_PASSWORD`; `AdminGetUser` showed `CONFIRMED`
  and the custom flow completed in one challenge.
- **The first exchange after the apply can fail.** `400 invalid_grant` with
  no trigger invoked, then success two minutes later on an identical call:
  the pool's permission to invoke its triggers had just been created. The
  front door now logs the exception class and Cognito's error code (never the
  token) so this is diagnosable, and the runbook says to retry.
- **A refresh reaches the pre-token trigger** on a custom-auth-only client,
  see above. The trigger refuses any source other than
  `TokenGeneration_Authentication` with the exchange marker.
- **The gateway authorizer accepts an ID token** from the exchange pool
  because `aud` matches; Cedar's forbid denies it for lack of `customer_id`.
- **AgentCore Identity sends `scope`** in the exchange request, from the
  `scopes` argument of `GetResourceOauth2Token`, and nothing about audience.
- **The pool cannot be given its own ids at deploy time** (it references the
  trigger Lambdas), so the functions read them from an SSM parameter written
  after the pool exists.
- **Cognito lets a trigger add `aud`** to an access token only as the
  session's app client id, and refuses `sub`, `username`, `exp`; complex claim
  values are accepted. All as documented, all confirmed by the minted token.
- From the earlier designs, still true: the gateway fetches a discovery
  document at create time and parses it as OIDC; the Cedar permit must follow
  the target and the forbid must follow the permit; `GetResourceOauth2Token`
  reads the provider's managed secret in the caller's context; an explicit
  workload identity works for the token call; the first cold start can
  exceed 120 seconds.

## External review (gpt-5.6-sol via the OpenAI API), 2026-09-11

Two rounds before the exchange pool went near AWS, then the post rounds.

- **Design review**, on the spec. Verdict: not safe to build as specified.
  Five blocking findings, all adopted: the pool's app client had to be
  confidential (a public custom-auth client is callable by anyone who knows
  its id, skipping the front door), with `SECRET_HASH` on both admin calls;
  the Terraform cycle (pool → triggers → pool ids) broken by an SSM parameter
  the functions read at runtime; explicit `token_validity_units`; exactly
  `ALLOW_CUSTOM_AUTH`, never a conditional refresh flow; and the service
  user's status verified live (the reviewer expected `FORCE_CHANGE_PASSWORD`;
  it was `CONFIRMED`). Also adopted: the challenge answer bound to the
  metadata copy (the reviewer proposed an HMAC assertion; equality in the
  verify trigger achieves the binding without a shared key), a leeway-free
  minimum-remaining-life check on the subject token, the `hasTag` guard kept
  in Cedar, one role per secret, pre-created log groups with no
  `CreateLogGroup`, `source_account` on the trigger permissions. Corrections
  to the spec's description of the AWS sample: it rotates across 24 service
  identities, accepts an ID token as a fallback subject, its pre-token
  enrichment is fail-open when the exchange metadata is absent, its pool also
  has a client with password and refresh flows, and it fronts a REST API
  with a separate authorizer.
- **Code review**, on the built code, Terraform and the live results.
  Verdict: safe to publish as a teaching demo with the stated caveats. All
  prior findings resolved or demonstrated live. Applied from its findings:
  the front door refuses a minted token whose `ExpiresIn` or `exp - iat`
  exceeds 330 s, so a drifted client setting fails rather than issues; the
  `policy_mode` variable validated to `ENFORCE` or `LOG_ONLY`; the trigger
  comment no longer implies the trigger source proves the custom flow ran;
  the runbook's readiness note; the live tests it asked for (refresh, SRP,
  admin password, the ID token at the gateway, expiry, the expected direct
  path), recorded above. From the post review's round 12: the front door
  now refuses any parameter outside the RFC 8693 set rather than ignoring
  it, tested and confirmed live, and the agent path re-run after the
  redeploy (7 orders). Accepted as demo simplifications: one role for the
  four triggers; the HTTP API's `/*/*` invoke permission; the six-hour JWKS
  stale bound; the five-minute secret cache. Its list of claims the post
  must not make was applied to the post.

### Post review rounds, 2026-09-11

The post, runbook, agent and Terraform were reviewed together after each
live run, with the same reviewer. Rounds 1 to 11 were on the KMS-signed
design (history below) and shaped the prose that carried over; the
exchange-pool rewrite was then reviewed afresh, rounds 12 onward.

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
- **Rounds 12 to 16**, on the exchange-pool rewrite. Round 12 had two
  blockers: the post said the token was usable "only at the order gateway"
  when any verifier configured for the exchange pool and the orders client's
  audience accepts it (reworded everywhere, with isolation between
  downstreams stated as one app client per service); and the AWS sample was
  described as if it had this demo's hardening (now attributed for its
  architecture only, with a paragraph of material differences). Also from
  that round: the front door now refuses any parameter outside the RFC 8693
  set rather than ignoring it, tested and confirmed live; the token's
  subject is "the exchange pool's fixed service user"; identity.py and the
  tenancy test say the trigger copies the customer's verified username into
  `customer_id`; the app-client secret's compromise boundary names
  Terraform state and `DescribeUserPoolClient`; "narrow token-exchange
  endpoint" with an explicit no-conformance sentence; the ID-token sentence
  credits default deny as well as the forbid; the stale gateway.tf comment
  and its front-door `depends_on` removed; the TL;DR cut to three sentences.
  Round 13: section 6 retitled "What limits the token's use at another
  service"; the lifetime sentence made accurate (not capped to the customer
  token, sign-out and revocation do not reach it); key custody stated as AWS
  managing the pool's keys rather than "rotates them"; "one flow" corrected
  to the explicit-flow list plus the trigger's refusal of refresh; "honestly
  secure" replaced. Round 14: the secret sentence in section 6 and the
  provider's use of the discovery shim narrowed to the evidence. Round 15,
  a new blocker: the customer's token in `ClientMetadata`, which Cognito's
  API reference says not to use for sensitive information. Kept as the
  sample's compromise, quoted, named as the part not to copy, with the
  handle-and-record shape a real exchange needs described. Round 16: "No
  material findings remain. Verdict: ready to publish."

## History: the KMS-signed issuer, 2026-09-11 (replaced the same day)

The second cut of the on-behalf-of design had the exchange service sign the
minted token itself with a KMS `ECC_NIST_P256` key (ES256, `sub` the
customer, `act` the registered client, `min(5 min, subject remaining)`
lifetime, its own JWKS). It was deployed on images `2e36c2d` then `f989799`,
verified live (the same chain and probes), published (demos PR #58, #59;
website PR #53, #54), and replaced within hours by the exchange-pool design
above, after Andy asked why the AWS sample's architecture was not being
followed with this design's properties added on top. It was; the answer was
to do exactly that.

What it got right carried over: the strict subject-token validator, the
bounded-stale JWKS cache, the request contract, the audience, the honest
limits. What it could not have: Cognito's key custody and rotation, and a
front door that cannot mint on its own. Its reviews:

- **Design review**: not safe to build as specified, because with
  `ActorTokenContent = NONE` the service authenticates a client secret and
  cannot truthfully mint an `act` claim naming the agent workload. Fixed:
  `act` named the registered client. Also adopted: signing bound to the
  immutable KMS key ARN; strict JWT validation with the algorithm pinned and
  `jku`/`x5u`/embedded keys/`crit` rejected; validate-before-replace JWKS
  caching; output lifetime `min(5 min, subject remaining)`; request
  parameters never choose audience, scope, key or claims; honest framing that
  KMS prevents key export, not signing by a compromised process. Its
  correction that the flow enum is `ON_BEHALF_OF` was wrong; boto3 and the
  live call confirm `ON_BEHALF_OF_TOKEN_EXCHANGE`.
- **Code review**: no forgery path. Blocker fixed: the JWK bound to the
  immutable key ARN and the `Sign` response's `KeyId` verified. Adopted:
  configuration validated at startup; P-256 coordinates fixed to 32 octets;
  strict NumericDate types; strict form parsing; a `WWW-Authenticate`
  challenge. The must-not-claim list (KMS prevents forgery; only AgentCore
  can call `/token`; `jti` prevents replay; `act` identifies the workload;
  scope-limited; categorically safer than relaying) shaped the prose.

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
