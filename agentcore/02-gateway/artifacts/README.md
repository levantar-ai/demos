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
