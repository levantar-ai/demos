# The AgentCore Runtime itself. Uses the awscc provider (Cloud Control API);
# the hashicorp/aws provider does not yet cover AgentCore Runtime.

resource "awscc_bedrockagentcore_runtime" "agent" {
  agent_runtime_name = local.runtime_name
  role_arn           = aws_iam_role.runtime.arn

  agent_runtime_artifact = {
    container_configuration = {
      container_uri = "${aws_ecr_repository.agent.repository_url}:${var.image_tag}"
    }
  }

  network_configuration = {
    network_mode = "PUBLIC"
  }

  protocol_configuration = "HTTP"

  tags = {
    Project = "demos"
    Demo    = local.demo_slug
  }
}
