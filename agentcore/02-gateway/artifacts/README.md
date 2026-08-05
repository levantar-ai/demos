# Deployment artifacts — captured from a real run

Captured from an actual deploy → invoke → destroy cycle of this demo on
2026-07-24 (region `us-east-1`). Raw material for the post.

## Deploy

16 resources, all created on the first apply. Notable timings: gateway 2s,
gateway target 14s, runtime 8s, Lambda 15s.

## Invocations (through the runtime)

| Prompt | Response |
|--------|----------|
| where is order 42? | `{"result": "order 42: {\"status\":\"shipped\",\"carrier\":\"DPD\",\"eta\":\"2026-07-28\"}"}` |
| what happened to order 44 | `{"result": "order 44: {\"status\":\"delivered\",\"carrier\":\"Royal Mail\",\"eta\":null}"}` |
| is order 99 ok? | `{"result": "order 99: {\"error\":\"order 99 not found\"}"}` |

First invocation on a fresh session: 2.74s wall-clock including microVM
cold start, token fetch, tools/list and tools/call.

## Direct MCP call (curl with a Cognito client-credentials token)

[`gateway-tools-list.json`](gateway-tools-list.json) — the gateway's
`tools/list` response, showing the `orders___lookup_order` namespacing
(`<target>___<tool>`, triple underscore).

## Review-fix verification (2026-07-24, second cycle)

After an external review: added `allowed_scopes` to the gateway authorizer,
trimmed the runtime role (removed unused Bedrock model and workload
identity permissions), and switched tool matching to
`endswith("___lookup_order")`. Redeployed (16 resources, first apply) and
verified: agent answered order 43 end to end, and an unauthenticated call
to the gateway returned HTTP 401. Destroyed after.

## Notes

- Gateway requires an authorizer; CUSTOM_JWT against the Cognito pool's
  discovery URL with an allowed client id list worked first time.
- The token request must include the resource-server scope
  (`demos-gateway/invoke`) or Cognito refuses the client-credentials grant.
- The tool Lambda receives the tool arguments as its event; the runtime
  passes gateway endpoint + credentials to the agent as environment
  variables from Terraform.

## Security rework (2026-07-24, third cycle)

Cognito and the client secret removed entirely; gateway switched to the
AWS_IAM authorizer and the agent signs MCP calls with SigV4 from the
runtime execution role (bedrock-agentcore:InvokeGateway scoped to the
gateway ARN). Verified live: 11-resource apply, order 42 answered end to
end (7.39s fresh session), unsigned request rejected with HTTP 401.
Video re-recorded against this stack. No credentials exist in code,
Terraform, state, or the runtime environment.

## Back to Cognito, and its review (gpt-5.6, fifth cycle, 2026-08-05)

Reverted the third-cycle IAM rework: the hand-rolled SigV4 client was
replaced with the stock MCP SDK over a Cognito bearer token, so the
gateway is `CUSTOM_JWT` again. Deployed and verified live: order 42
answered end to end (8s fresh session, 2s warm), order 99 missing,
unauthenticated and bogus-token requests both rejected with HTTP 401.

Seventeen review findings, actioned:

- **high** the client secret sat in Terraform state twice. Secrets Manager
  version now written with `secret_string_wo` (write-only), removing one
  copy. `aws_cognito_user_pool_client.client_secret` is a computed
  attribute and cannot be suppressed, so one copy remains and the post
  now says so instead of implying the problem is solved
- `allowed_scopes` restored on the authorizer (regressed from cycle two)
- token cache guarded by a lock with double-checked expiry, since the
  server is threaded and a burst at expiry would stampede
- client credentials moved to `Authorization: Basic`, out of the form body
- `result.isError` and non-text content handled; a tool error was being
  returned to the caller as an answer
- `Content-Length` validated, 64KB cap, 413 on oversize
- order regex anchored on the word "order": "in 2 days, where is order
  42?" previously looked up order **2**
- prose: authenticated is not authorised (same workload identity for every
  call, no per-order entitlement); gateway-level scopes mean a accepted
  token reaches every target; the agent invokes a known tool name rather
  than discovering it; the MCP client does not sign SigV4; least-privilege
  claim narrowed to what the published code shows
- the 401 test now uses `tools/call` rather than `tools/list`, which never
  reaches a backend even when it succeeds, so rejecting one proved less
  than the post claimed

Not actioned: a missing order still returns as a successful tool result
rather than a protocol error, which reads as the correct modelling for a
domain-level miss.

## Re-review of the IAM rework (gpt-5.6, fourth cycle)

Seven findings, all actioned: credentials wording corrected (rotated
role temporaries vs static secrets), InvokeGateway scoped to the exact
gateway ARN, frozen credential snapshot for thread-safe signing,
botocore pinned directly, prompt type guards (all three demos), stale
Cognito comment removed, Identity sentence narrowed. Verified on
camera: 11-resource apply, both order lookups, unsigned request 401.
