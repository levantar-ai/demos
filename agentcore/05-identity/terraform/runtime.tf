# The AgentCore Runtime, as post 01, now checking who is calling.
#
# With a JWT authorizer the runtime validates every caller's bearer token
# against the pool's discovery document before the request reaches the
# agent, and IAM SigV4 invocation is off. The Authorization header is
# forwarded to the container so the agent can read the verified claims and
# relay the same token to the gateway.

resource "aws_bedrockagentcore_agent_runtime" "agent" {
  agent_runtime_name = local.runtime_name
  role_arn           = aws_iam_role.runtime.arn

  agent_runtime_artifact {
    container_configuration {
      container_uri = "${aws_ecr_repository.agent.repository_url}:${var.image_tag}"
    }
  }

  network_configuration {
    network_mode = "PUBLIC"
  }

  protocol_configuration {
    server_protocol = "HTTP"
  }

  authorizer_configuration {
    custom_jwt_authorizer {
      discovery_url   = local.discovery_url
      allowed_clients = [aws_cognito_user_pool_client.customers.id]
    }
  }

  request_header_configuration {
    request_header_allowlist = ["Authorization"]
  }

  environment_variables = {
    CODE_INTERPRETER_ID = aws_bedrockagentcore_code_interpreter.sandbox.code_interpreter_id
    GATEWAY_URL         = aws_bedrockagentcore_gateway.orders.gateway_url
    MEMORY_ID           = aws_bedrockagentcore_memory.agent.id
  }

  tags = {
    Project = "demos"
    Demo    = local.demo_slug
  }
}
