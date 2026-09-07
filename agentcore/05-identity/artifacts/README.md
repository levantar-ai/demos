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
