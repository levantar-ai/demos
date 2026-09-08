# Policy in AgentCore. The engine evaluates Cedar policies at the gateway on
# every tool call, before the target Lambda runs, outside the agent's code.
# The caller is the customer the gateway authenticated, so a call the agent
# makes for anyone other than that customer is denied here regardless of what
# the agent or a model decided to ask for.

resource "aws_bedrockagentcore_policy_engine" "orders" {
  name        = "demos_agentcore_05_orders"
  description = "Per-customer authorization for the orders gateway"

  tags = {
    Project = "demos"
    Demo    = local.demo_slug
  }
}

# Cedar. The principal is the customer, from the token's sub, and the
# verified username claim is a principal tag. The tool's customer_id argument
# is context.input.customer_id. This permits list_orders only when the
# argument matches the caller's own username, and Cedar is default-deny, so a
# mismatched customer_id has no permit and is refused.
resource "aws_bedrockagentcore_policy" "own_orders" {
  name             = "own_orders_only"
  policy_engine_id = aws_bedrockagentcore_policy_engine.orders.policy_engine_id
  description      = "A customer may list only their own orders"

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

# Cedar permits are additive, so a broad permit added in a later post could
# otherwise authorise a cross-customer call. This forbid, which wins over any
# permit, keeps the invariant: the action is refused whenever the customer_id
# argument is not the caller's own username.
resource "aws_bedrockagentcore_policy" "deny_other_orders" {
  name             = "deny_other_customers_orders"
  policy_engine_id = aws_bedrockagentcore_policy_engine.orders.policy_engine_id
  description      = "Forbid list_orders for any customer_id that is not the caller"

  definition {
    cedar {
      statement = <<-CEDAR
        forbid(
          principal is AgentCore::OAuthUser,
          action == AgentCore::Action::"orders___list_orders",
          resource == AgentCore::Gateway::"${aws_bedrockagentcore_gateway.orders.gateway_arn}"
        ) unless {
          principal.hasTag("username") &&
          principal.getTag("username") == context.input.customer_id
        };
      CEDAR
    }
  }
}
