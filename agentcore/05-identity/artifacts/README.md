# Deployment artifacts — captured from a real run

Captured from a deploy → invoke cycle of this demo on 2026-09-07 (region
`us-east-1`), image tag `1dc054e`.

## Deploy

20 resources on top of the ECR repository. The memory store and its
strategy were the slow ones again, two and a half minutes. The credential
provider, the runtime and the gateway each created in seconds.

## First invocation, and the IAM gap it found

The first `list my orders` as `c-1000` hung for two minutes and returned
`HTTP 424 {"message":"Runtime initialization time exceeded. Please make
sure that initialization completes in 120s."}`. The runtime log showed the
container answering 502 to a POST every two seconds with:

```
AccessDeniedException when calling the GetResourceOauth2Token operation:
Access denied when retrieving secret 'arn:aws:secretsmanager:us-east-1:…:secret:bedrock-agentcore-identity!default/oauth2/demos-agentcore-05-identity-gateway-…'.
User: arn:aws:sts::…:assumed-role/demos-agentcore-05-identity-runtime/… is not authorized to perform: secretsmanager:GetSecretValue
```

Two facts came out of that. The token vault reads the client secret with
the caller's role, so the runtime role needs `secretsmanager:GetSecretValue`
on the provider's `client_secret_arn`. And the runtime treats a 5xx from
the container on a new session as a failed initialisation and retries until
the 120s limit, so the caller sees a timeout rather than the error. Fixed
with one IAM statement, no image change.

## Identity from the token

Access token claims for `c-1000` (`sub`, `jti` and friends elided):

```json
{"iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_…",
 "client_id": "<customers client>", "token_use": "access",
 "scope": "aws.cognito.signin.user.admin", "username": "c-1000"}
```

- `list my orders` as `c-1000` returned seven orders, all `customer_id`
  `c-1000`, ids 1033, 1038, 1059, 1084, 1218, 1242, 1255.
- `where is order 1255?` as `c-1000` returned that order. `where is order
  1014?` returned `{"error": "order 1014 is not on your account"}`.
- `list my orders` as `c-1001` returned c-1001's orders. `where is order
  1255?` as `c-1001` returned `not on your account`.
- `remember: I prefer DPD, leave parcels with the neighbour` sent with
  `"actor": "c-1001"` in the body as `c-1000` was stored under actor
  `c-1000`, confirmed with `list-events --actor-id c-1000`. `recap` as
  `c-1000` returned it, `recap` as `c-1001` returned `[]`.
- `payload.json` (the post 04 CSV) as `c-1000` returned the same
  `describe()` table and `rows: 8` as post 04.

## Negative paths at the runtime

- No `Authorization` header: `HTTP/2 401`, `www-authenticate: Bearer
  resource_metadata="…/invocations/.well-known/oauth-protected-resource?qualifier=DEFAULT"`,
  body `{"jsonrpc":"2.0","error":{"code":-32001,"message":"Missing
  Authentication Token"}}`.
- `Bearer not.a.token`: `HTTP 403 {"message":"OAuth authorization failed:
  Failed to parse token"}`.
- The agent's own M2M token (client_credentials from the agent app
  client, valid for the gateway): `HTTP 401 {"jsonrpc":"2.0","error":
  {"code":-32001,"message":"Claim 'client_id' value mismatch with
  configuration."}}`. The runtime enforces `allowed_clients`.
- No session id header at all: `HTTP 200`, the service allocates one. A
  five-character one: `HTTP 400 ... 'runtimeSessionId' failed to satisfy
  constraint: Member must have length greater than or equal to 33`.
- `aws cognito-idp sign-up` against the customers client, after the pool
  was set to admin-only creation: `NotAuthorizedException: SignUp is not
  permitted for this user pool`.
- The SigV4 CLI, `aws bedrock-agentcore invoke-agent-runtime`, as the
  earlier posts used it: `AccessDeniedException ... Authorization method
  mismatch. The agent is configured for a different authorization method
  than what was used in your request.` A runtime takes one or the other.

## Gotchas

- `client_secret_arn` on the credential provider resource is a nested
  block, so the IAM reference is
  `one(...client_secret_arn).secret_arn`, not the attribute itself.
  A bare reference produces `MalformedPolicyDocument: Syntax errors in
  policy` at apply.
- The workload identity the runtime creates is named
  `<runtime name>-<id>`, so the IAM pattern `<runtime name>-*` from the AWS
  docs matches it and avoids a dependency from the role policy on the
  runtime.
- `namespaces` on `aws_bedrockagentcore_memory_strategy` is deprecated in
  provider 6.63 in favour of `namespace_templates`, changed here.

## Internal review, 2026-09-07

Three adversarial passes (AWS facts, code and prose consistency, voice)
before the external review. Findings actioned:

- The pool allowed self sign-up by default, so anyone holding the public
  customers client id could have registered a customer id before its
  owner and Brightwell's `admin-create-user` would then have failed. Now
  `allow_admin_create_user_only = true`, verified live (above).
- `lookup_order` was still on the gateway target, answering for any order
  id to whoever held the agent's token, with nothing calling it. Removed
  from the target and the Lambda; the target exposes `list_orders` only.
- The post claimed to close post 02's gap outright. The gateway and Lambda
  still see only the agent's identity, the scoping lives in the agent.
  The post now says so, in the intro and the conclusion.
- "never persisted in state" was wrong, the Cognito client resource holds
  the secret as a computed attribute. Narrowed to what write-only actually
  does.
- The session id header was described as required. Tested, it is optional
  and the 33-character rule applies when it is sent. NOTE reworded.
- The 3LO sentence had the vault handling consent. It hands back an
  authorization URL for the customer the first time. Reworded.
- The credential provider snippet in the post had dropped the load-bearing
  `depends_on` on the pool domain. Restored, with a sentence on why.
- The agent's comment on the workload token header cited the SDK
  loosely. Now cites the SDK source and says why both names are read.
- Post 04's closing line promised outbound OAuth on a user's behalf, which
  this post defers. Softened to what 05 delivers.
- Twelve voice edits, mostly the intro re-explaining posts 02 and 03, a
  duplicated forward pointer, and a NOTE repeating its own paragraph.

## External review (gpt-5.6-sol via OpenAI API), 2026-09-07

Three rounds. Round one, nine findings, two blockers, all actioned except
one declined. Round two, seven, all actioned. Round three, seven, six
actioned and one declined.

Actioned, in rough order of weight:

- The post claimed to close post 02's gateway gap and promised post 06's
  model calls would be scoped to the customer. The gateway and Lambda
  still only see the agent's identity. The post now says the scope is
  enforced in the agent's code, does not reach the gateway, and that post
  06 has to inject the customer id from the verified token and keep it
  out of any model-controlled tool argument.
- "the agent's code never handles a secret" and "the execution role no
  longer reads a secret" overstated the vault. The role has GetSecretValue
  on the vault's copy, so a compromised agent could read it. The post, the
  TL;DR and the identity.tf comment now say credentials stay out of the
  code, not away from the role, and that the Cognito client's computed
  secret is still in state.
- "every caller is a known customer" rested on admin-only provisioning the
  post did not show. The pool setting is now in the post with the reason.
- The agent accepted any token with a username claim. It now requires
  `token_use == "access"`, with tests for an ID token and a missing claim.
- The fallback 401 in the agent was described as protection against a
  misconfigured authorizer. It is not, a forged payload passes it. The
  post now says so and names the runtime's authorizer as the only control.
- The handler responded 401 before reading the body, which could race a
  client mid-upload. The body is read first now, with a 200KB test.
- USER_PASSWORD_AUTH was presented as the natural customer design. Now
  labelled a CLI convenience with managed login, authorization code and
  PKCE named for a customer-facing app.
- The workload token was described as carrying the customer identity,
  which the M2M run does not demonstrate. Bounded to "represents the
  workload identity, treated as opaque" in the post and the code.
- USER_FEDERATION was described as the vault handling consent. Now named
  as not built, with the provider registration and callback URL it needs.
- Section 4 used $POOL, $CLIENT_ID, $INVOKE_URL, $SESSION and $PASSWORD
  without defining them, omitted --region, and the README hard-coded the
  region and never set PASSWORD. Both now start from the Terraform outputs
  including a new aws_region output, read the password with read -rsp,
  unset it after the token, and show the cd into the demo directory.
- The 1014 example was a bare -d fragment in a bash block. Full command.
- The abridged response was tagged json. Untagged and labelled abridged.
- The diagram's agent to Identity edge was labelled with the returned
  token. Relabelled with the call and what is sent.
- The gateway.py docstring said the agent sees "the access token and
  nothing else". Now says the call does not return the client secret.

Declined:

- Replace `aws-vault exec lev:andy.rea --` in the README with plain
  commands. It is the convention across every demo README in the series
  and the author's instruction.
- Narrow the runtime and gateway roles' trust policy SourceArn from
  `bedrock-agentcore:region:account:*` to the runtime and gateway ARN
  namespaces. It is AWS's documented trust policy, carried forward from
  post 01 across every demo, and not this post's subject. Worth a
  series-wide change with a live check that the service's source ARN
  matches the narrower pattern, not a change in one demo.

No further redeploy for the prose. The code changes (token_use check,
body-first ordering, comment and docstring) and the Terraform changes
(admin-only pool, single tool on the target, aws_region output) are in
the final image and apply, and the checks above were re-run against it.
