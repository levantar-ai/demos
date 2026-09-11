# The gateway: fronts the tool Lambda as an MCP server, authenticating
# callers with the resource JWT the exchange issuer (exchange.tf) mints. It
# does not accept the customer's Cognito token; that is validated by the
# runtime only.

resource "aws_iam_role" "gateway" {
  name = "${local.name_prefix}-gateway"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "bedrock-agentcore.amazonaws.com" }
        Action    = "sts:AssumeRole"
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
          ArnLike = {
            "aws:SourceArn" = "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:gateway/*"
          }
        }
      }
    ]
  })

  tags = {
    Project = "demos"
    Demo    = local.demo_slug
  }
}

resource "aws_iam_role_policy" "gateway" {
  name = "invoke-tools"
  role = aws_iam_role.gateway.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction"]
        Resource = aws_lambda_function.tool.arn
      },
      {
        # The gateway loads and evaluates its policy engine on every call.
        # These are scoped to this one engine.
        Effect = "Allow"
        Action = [
          "bedrock-agentcore:GetPolicyEngine",
          "bedrock-agentcore:GetPolicyEngineSummary",
          "bedrock-agentcore:ListPolicies",
          "bedrock-agentcore:GetPolicy"
        ]
        Resource = aws_bedrockagentcore_policy_engine.orders.policy_engine_arn
      },
      {
        # The two evaluation actions do not support resource-level scoping,
        # so they are granted on "*", which is account-wide. The read actions
        # above are scoped to this engine, but that does not constrain what
        # a principal holding this role could ask these two to evaluate.
        Effect = "Allow"
        Action = [
          "bedrock-agentcore:AuthorizeAction",
          "bedrock-agentcore:PartiallyAuthorizeActions"
        ]
        Resource = "*"
      }
    ]
  })
}

# CUSTOM_JWT against the exchange service's issuer. The agent does not relay
# the customer's raw Cognito token here; it presents the on-behalf-of token
# that AgentCore Identity brokered from it and the exchange service minted.
# That token carries an audience (unlike a Cognito access token), so the
# gateway validates it by discovery against that issuer and by allowed_audience.
# The token carries the customer's username, so the caller the gateway
# establishes is still the customer, not the agent.
# authorizer_type is immutable; changing it later means replacing the gateway.
#
# The policy engine is what enforces per-customer access. It evaluates a
# Cedar policy on every tool call, before the target runs, using the caller
# established here. See policy.tf.
resource "aws_bedrockagentcore_gateway" "orders" {
  name            = "${local.name_prefix}-gw"
  role_arn        = aws_iam_role.gateway.arn
  protocol_type   = "MCP"
  authorizer_type = "CUSTOM_JWT"

  authorizer_configuration {
    custom_jwt_authorizer {
      discovery_url    = "${local.exchange_issuer}/.well-known/openid-configuration"
      allowed_audience = [local.orders_audience]
    }
  }

  policy_engine_configuration {
    arn  = aws_bedrockagentcore_policy_engine.orders.policy_engine_arn
    mode = var.policy_mode
  }

  # The authorizer's discovery URL is the exchange service. Only the API
  # resource is referenced above, so make the routes, Lambda permission and
  # stage explicit dependencies: the discovery document must be serving before
  # the gateway is created, in case AgentCore fetches it at create time.
  depends_on = [
    aws_apigatewayv2_stage.exchange,
    aws_apigatewayv2_route.exchange,
    aws_lambda_permission.exchange,
  ]
}

resource "aws_bedrockagentcore_gateway_target" "orders" {
  gateway_identifier = aws_bedrockagentcore_gateway.orders.gateway_id
  name               = "orders"

  credential_provider_configuration {
    gateway_iam_role {}
  }

  target_configuration {
    mcp {
      lambda {
        lambda_arn = aws_lambda_function.tool.arn

        # One tool, scoped to a customer. Post 02's lookup_order took any
        # order id and answered for any customer, which nothing scoped to
        # a caller can use, so it is not carried forward.
        tool_schema {
          inline_payload {
            name        = "list_orders"
            description = "List every order on a customer's account, with totals and status"

            input_schema {
              type = "object"

              property {
                name        = "customer_id"
                type        = "string"
                description = "The customer id whose orders to list"
                required    = true
              }
            }
          }
        }
      }
    }
  }
}
