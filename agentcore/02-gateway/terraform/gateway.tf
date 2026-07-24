# The gateway: fronts the tool Lambda as an MCP server, validating caller
# JWTs against the Cognito user pool.

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
      }
    ]
  })
}

resource "aws_bedrockagentcore_gateway" "orders" {
  name            = "${local.name_prefix}-gw"
  role_arn        = aws_iam_role.gateway.arn
  protocol_type   = "MCP"
  authorizer_type = "CUSTOM_JWT"

  authorizer_configuration {
    custom_jwt_authorizer {
      discovery_url   = local.discovery_url
      allowed_clients = [aws_cognito_user_pool_client.agent.id]
    }
  }
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

        tool_schema {
          inline_payload {
            name        = "lookup_order"
            description = "Look up the status of an order by its order id"

            input_schema {
              type = "object"

              property {
                name        = "order_id"
                type        = "string"
                description = "The order id to look up"
                required    = true
              }
            }
          }
        }
      }
    }
  }
}
