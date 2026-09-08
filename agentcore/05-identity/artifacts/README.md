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

## Round-four hardening (gpt-5.6), 2026-09-08

- The runtime and gateway role trust policies had `aws:SourceArn` as the
  account-wide `…:*`. Narrowed to `…:runtime/*` and `…:gateway/*`
  respectively, and verified live that the agent still lists orders and the
  gateway still denies a cross-customer call, so the tighter confused-deputy
  scope holds.
- An ID token is refused at the JWT authorizer, not at Cedar: a live call
  with the customer's ID token returned `401 Claim 'client_id' value
  mismatch`, because a Cognito ID token has no `client_id` claim and the
  authorizer validates `allowed_clients`. The handler's `token_use` check is
  a second line behind that.

## External review (gpt-5.6-sol via OpenAI API), 2026-09-08

Five rounds, focused on the security of the design as much as the prose,
because the post's subject is doing agent identity safely.

- Round one, fourteen findings, three blockers. The Cedar boundary covers
  only the orders gateway tool, so claims of enforcing all customer data were
  scoped down and memory and the sandbox called out as still agent-scoped;
  the "no credential / compromised agent" language was narrowed to what the
  gateway guarantees; `LOG_ONLY` was reframed as fail-open. A `forbid` guard
  was added so the invariant survives future additive permits.
- Round two, five findings. Enforcement claims scoped in the TL;DR and
  conclusion; the two Cedar policies reflected everywhere; precise vault,
  IAM-scoping, RFC 8693 versus 7523 and web-identity wording.
- Round three, one blocker and five more. The conclusion's compromised-agent
  claim made consistent with the caveat; the username-versus-`sub` lifecycle
  assumption stated; the web-identity alternative given its trust and Scan
  constraints; the README installs the MCP client for the probe.
- Round four, three findings. The ID-token refusal re-attributed to the JWT
  authorizer with the live 401 as evidence; the role trust policies narrowed
  to `runtime/*` and `gateway/*` and re-verified live; the password-argv note
  qualified.
- Round five, clean. Verdict: ready to publish, no remaining blocker or
  should-fix issue in the security design, AWS claims, implementation or
  walkthrough.

No redeploy was needed for the prose rounds. The two live changes, the
`forbid` policy and the tightened trust policies, were applied and verified
against the running stack, image `f32c415`.

## Section 6 added and reviewed (gpt-5.6), 2026-09-08

A reader asked whether passing a short-lived Cognito bearer token to an
autonomous agent is safe (attribution, prompt injection, bearer replay). A
section 6, "What it does not solve, and where it fits", was added: Cedar
answers the wrong-customer vector, the bearer token is mitigated but not
neutralised, attribution is weaker than an on-behalf-of exchange, and a
comparison table plus the Well-Architected mapping. Reviewed over three
rounds. Corrections made: OBO's actor attribution is provider-dependent, not
guaranteed (RFC 8693 defines `act` but does not require it, RFC 7523 does
not define it); the Lambda sees the approved `customer_id` and the gateway
role, not the customer principal; expiry alone bounds replay while TLS and
non-persistence lower disclosure; guardrails/tracing/evals help but are not a
hard boundary on returned data; AGENTSEC02 enforcement is at the gateway and
policy engine, scoped to the orders tool. Verdict: ready to publish.
