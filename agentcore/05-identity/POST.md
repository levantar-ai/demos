# Knowing who your agent is acting for, with AgentCore Identity

## TL;DR;

How to establish who a customer is on the way into an agent with AgentCore
Identity, and then enforce that identity on every tool call with Policy in
AgentCore, so a Cedar policy at the gateway refuses any call outside the
caller's own data, before the tool runs and outside the agent's code.

> SOURCE CODE - All code for this post is available at:
> https://github.com/levantar-ai/demos/tree/main/agentcore/05-identity

## Longer version

This series is building one thing, the order support agent for Brightwell,
a small online retailer of outdoor kit that ships with DPD and Royal Mail.
Posts 01 to 04 gave it a runtime, a tool that looks orders up, memory and a
sandbox. None of them knew who was asking, and post 02 said so at the time,
that the gateway established a legitimate client was calling, not that it
was entitled to a particular order.

Closing that gap safely is the whole of this post, and it matters because
identity is where agent security is won or lost. The tempting fix, giving
the agent a broad credential and filtering results in its own code, is the
one AWS's Well-Architected Agentic AI Lens tells you not to reach for.

> The traditional approach of granting the agent broad credentials and
> relying on application-level filtering (such as adding WHERE clauses to
> queries) creates a single point of failure. A more resilient design moves
> authorization enforcement out of the agent's application code and into the
> infrastructure layer wherever possible.

That is [AGENTSEC03](https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentsec03.html).
The reason it matters more for an agent than for ordinary code is the next
post, where a model, not deterministic code, chooses the arguments to a
tool. If the only thing keeping a caller to their own orders is the agent
passing the right id, a model that can be talked into passing a different
one has just read someone else's account.

So this post does two things. AgentCore Identity establishes the customer
on the way in, and Policy in AgentCore enforces that customer on every tool
call at the gateway. The enforcement point is deliberately not the agent.

![Architecture](architecture.png)

## 1 - Inbound, the runtime and the gateway check the customer

The Cognito pool from post 02 keeps a public client for customers, who sign
in with a password and get an access token. The runtime validates that
token before the agent sees the request, and forwards it, exactly as post
05's first cut did. What is new is that the gateway now validates the same
customer token rather than a token the agent minted for itself:

```hcl
authorizer_configuration {
  custom_jwt_authorizer {
    discovery_url   = local.discovery_url
    allowed_clients = [aws_cognito_user_pool_client.customers.id]
  }
}
```

A Cognito access token carries `client_id` and `username` but no `aud`, so
the gateway validates it by `allowed_clients` and no audience is set. The
caller the gateway establishes from that token is the customer, and their
username is Brightwell's customer id. That is the identity the next section
authorizes against.

> NOTE: this is the same pool for customer accounts that Brightwell already
> controls. Only an admin creates users, so a username is a real customer id
> and not something an attacker can register. `authorizer_type` is
> immutable, so a gateway that starts on the wrong client has to be replaced.

## 2 - The policy engine, and the one Cedar rule

Policy in AgentCore is a policy engine attached to the gateway. It holds
Cedar policies and evaluates them on every tool call. AWS states the model
plainly:

> For every tool invocation, the policy engine evaluates all applicable
> policies against the request to determine whether to allow or deny access.
> The engine enforces default-deny and forbid-wins semantics automatically.

That is from the
[Policy core concepts](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-core-concepts.html),
which also says where the principal and its attributes come from:

> When a AgentCore Gateway uses OAuth authorization, the principal is created
> from the JWT token's `sub` claim. OAuth principals support tags that
> contain JWT claims such as username, scope, role, etc.

So the caller's `sub` is the Cedar principal, the verified `username` claim
is a principal tag, and the tool's arguments arrive as `context.input`. One
rule expresses the whole policy, a customer may list only their own orders:

```hcl
resource "aws_bedrockagentcore_policy" "own_orders" {
  name             = "own_orders_only"
  policy_engine_id = aws_bedrockagentcore_policy_engine.orders.policy_engine_id

  definition {
    cedar {
      statement = <<-CEDAR
        permit(
          principal is AgentCore::OAuthUser,
          action == AgentCore::Action::"orders___list_orders",
          resource == AgentCore::Gateway::"${aws_bedrockagentcore_gateway.orders.gateway_arn}"
        ) when {
          principal.hasTag("username") &&
          principal.getTag("username") == context.input.customer_id
        };
      CEDAR
    }
  }
}
```

The `permit` only fires when the `customer_id` argument equals the caller's
own username. Because Cedar denies by default, a call for any other customer
matches no `permit` and is refused. The check is on the token's claim, which
the gateway verified, so it is not something the agent or a model can talk
its way around.

> NOTE: a tool-specific action must name a specific gateway resource, not a
> wildcard, or `CreatePolicy` refuses the statement. The gateway's role also
> needs the policy-engine read and evaluate actions, and the two evaluate
> actions, `AuthorizeAction` and `PartiallyAuthorizeActions`, do not take a
> resource, so they are granted on `*` while the engine itself stays scoped.

## 3 - The agent carries the token, not a credential

Since post 02 the agent minted its own gateway token from a client secret in
the vault. That is gone. The agent relays the customer's own token, the one
the runtime handed it, so it holds no broad credential of its own:

```python
def list_orders(customer_id, customer_token):
    return asyncio.run(
        _call_tool("list_orders", {"customer_id": customer_id}, customer_token)
    )
```

This is the shape AWS's Well-Architected lens asks for, the user's identity
travelling as claims rather than the agent standing in for the user:

> When an agent acts on behalf of a user, the user context propagates as
> signed token claims through the call chain without the agent ever assuming
> the user's credentials.

The agent still passes `customer_id`, and it still passes the verified one.
That belt is useful, but it is not the boundary. The gateway is, and it
holds even when the agent's own logic is wrong, which is the point of moving
the check out of the agent.

## 4 - Running it

A customer signs in and calls the agent, and the happy path is unremarkable,
`list my orders` returns their orders. The interesting call is the one that
should not work. Asking the gateway directly, with a customer's own token,
for another customer's orders:

```bash
GATEWAY_URL=... TOKEN=<c-1000's token> python3 probe_gateway.py c-1000
# allowed: 7 orders for c-1000

GATEWAY_URL=... TOKEN=<c-1000's token> python3 probe_gateway.py c-1001
# denied by the gateway: Tool Execution Denied: Tool call not allowed due to
# policy enforcement [No policy applies to the request (denied by default).]
```

The same token that reads c-1000's orders cannot read c-1001's, because the
Cedar policy has no `permit` for a `customer_id` that is not the caller's,
and default-deny does the rest. Nothing in the agent had to be correct for
that to hold. This is what AWS means when it explains why Policy in AgentCore
sits at the gateway:

> Centralizing authorization outside both gives you a single checkpoint the
> LLM can't circumvent; one that's auditable and can be verified independently
> of the application code.

<!-- -->

> NOTE: validate before you enforce. The engine takes a `LOG_ONLY` mode that
> evaluates and records decisions without acting on them, so you can confirm
> the principal, its tags and the decision are what you expect, then switch to
> `ENFORCE`. This demo's Terraform carries a `policy_mode` variable for that.

## 5 - When it is not a gateway tool

Policy at the gateway is the answer when the tool is behind the gateway,
which is where this series has put its tools since post 02. Two other
shapes come up, and both keep authorization out of the agent.

For a first-party AWS store such as DynamoDB, you do not need a policy engine
at all. Register the Cognito pool as an IAM OIDC provider, exchange the
customer's ID token for customer-scoped credentials with STS
`AssumeRoleWithWebIdentity`, and let IAM enforce which rows the agent can
read. The federation id comes from the signed token, so the agent cannot
widen it.

![Web-identity alternative](alt-aws.png)

For a third-party SaaS that IAM cannot reach, AgentCore Identity does carry
the delegation itself, through on-behalf-of token exchange. The agent
exchanges the customer's inbound token for a user-scoped token the SaaS
accepts, and the SaaS enforces its own sharing rules. It needs the provider
to support RFC 8693 token exchange, which Cognito does not, so it is the
answer for a Salesforce or an Entra, not for a first-party Cognito tool.

![On-behalf-of alternative](alt-saas.png)

## Conclusion

The agent now acts for a known customer, and it is the infrastructure that
keeps it there. AgentCore Identity establishes the customer at the runtime
and the gateway, Policy in AgentCore evaluates a Cedar policy on every tool
call, and a request for anyone else's orders is denied by default before the
tool runs. The agent holds no broad credential and its own code is not the
thing standing between a caller and someone else's account.

That is the precondition for the next post, where a Bedrock model is handed
the tools this series has built and asked a question nobody wrote code for.
It will choose the arguments to those tools, including the customer id, and
the reason that is safe is that the gateway, not the model, decides whose
orders come back.

References:

- https://github.com/levantar-ai/demos/tree/main/agentcore/05-identity
- https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentsec02-bp01.html
- https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentsec03.html
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-core-concepts.html
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-understanding-cedar.html
