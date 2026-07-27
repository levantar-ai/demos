# The AgentCore Runtime, as post 01, plus the environment the agent needs
# to reach the gateway.

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
    GATEWAY_URL = aws_bedrockagentcore_gateway.orders.gateway_url
  }

  tags = {
    Project = "demos"
    Demo    = local.demo_slug
  }
}
