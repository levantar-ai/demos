# Deployment artifacts — captured from a real run

Captured from a deploy and invoke cycle of this demo on 2026-09-08 (region
`us-east-1`), image tag `f32c415`, policy engine in `ENFORCE`.

## What was deployed

The gateway's authorizer was pointed at the customers client, a Policy
Engine (`demos_agentcore_05_orders`) was created with a `permit` policy (`own_orders_only`) and a `forbid`
guard (`deny_other_customers_orders`), and the gateway was attached to it. The OAuth2
credential provider, the token vault call, the agent Cognito client and the
resource server were all removed. The agent relays the customer's token.

## The Cedar policy

```
permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"orders___list_orders",
  resource == AgentCore::Gateway::"arn:aws:bedrock-agentcore:us-east-1:…:gateway/demos-agentcore-05-identity-gw-…"
) when {
  principal.hasTag("username") &&
  principal.getTag("username") == context.input.customer_id
};
```

## Validation, LOG_ONLY then ENFORCE

- In `LOG_ONLY`, a direct gateway call with c-1000's token for
  `customer_id=c-1000` returned c-1000's seven orders, and the same token for
  `customer_id=c-1001` returned c-1001's orders. The engine logs but does not
  act, which is the leak `ENFORCE` closes.
- Switched to `ENFORCE` and repeated. c-1000 for c-1000: allowed. c-1000 for
  c-1001: denied. With only the `permit`, the message was `[No policy applies
  to the request (denied by default).]`; after adding the `forbid` guard it is
  `[Policy evaluation denied due to deny_other_customers_orders].`, the
  forbid winning explicitly.
- Symmetric: c-1001's token for c-1001 allowed, for c-1000 denied.

## Through the agent

- `list my orders` as c-1000 returned c-1000's seven orders (1033, 1038,
  1059, 1084, 1218, 1242, 1255).
- `where is order 1086?` (a c-1001 order) as c-1000 returned `order 1086 is
  not on your account`, because the agent lists the caller's own orders,
  which the gateway permits, and filters.
- `payload.json` (the post 04 CSV) as c-1000 returned the same `describe()`
  table and `rows: 8`, so the sandbox still works behind the new inbound auth.

## Negative paths

- No `Authorization` header at the runtime: `HTTP 401`.
- The gateway deny above is the key result. The tool never runs for a
  mismatched customer id.

## IAM findings during the build

The gateway role needed, in order of discovery:

- `bedrock-agentcore:GetPolicyEngine` on the engine, or `UpdateGateway`
  fails to attach it.
- `bedrock-agentcore:AuthorizeAction`, which does not support resource-level
  scoping and had to be granted on `*` (a specific gateway ARN, even a
  matching wildcard, was denied).
- `bedrock-agentcore:PartiallyAuthorizeActions`, likewise on `*`.
- The read set (`GetPolicyEngine`, `GetPolicyEngineSummary`, `ListPolicies`,
  `GetPolicy`) stays scoped to the engine ARN.

Each addition raced IAM eventual consistency, so the first apply after adding
a permission failed with an access-denied and succeeded on a retry, as the
project's own guidance predicts.

## Cedar findings

- A tool-specific action (`orders___list_orders`) requires the resource to
  name a specific `AgentCore::Gateway`, not a wildcard, or `CreatePolicy`
  refuses it.
- The principal's `username` tag is populated from the Cognito access token's
  `username` claim, and `context.input.customer_id` is the tool argument, so
  the equality check works as written. Confirmed by the allow and deny above.
- A second policy, a `forbid` with the same condition negated, was added so
  the invariant survives any future additive `permit` (forbid wins). With it,
  a mismatched call is denied explicitly by `deny_other_customers_orders`
  rather than by default.
