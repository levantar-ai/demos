# The AgentCore Runtime, as post 01, plus the memory id the agent needs.

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

  environment_variables = {
    MEMORY_ID         = aws_bedrockagentcore_memory.agent.id
    GATEWAY_URL       = aws_bedrockagentcore_gateway.orders.gateway_url
    TOKEN_URL         = "https://${aws_cognito_user_pool_domain.agents.domain}.auth.${var.aws_region}.amazoncognito.com/oauth2/token"
    TOKEN_SCOPE       = "${aws_cognito_resource_server.orders.identifier}/invoke"
    CLIENT_SECRET_ARN = aws_secretsmanager_secret.agent_client.arn
  }

  tags = {
    Project = "demos"
    Demo    = local.demo_slug
  }
}
