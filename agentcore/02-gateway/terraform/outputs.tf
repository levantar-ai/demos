output "runtime_arn" {
  description = "ARN of the deployed AgentCore runtime"
  value       = aws_bedrockagentcore_agent_runtime.agent.agent_runtime_arn
}

output "gateway_url" {
  description = "MCP endpoint of the gateway"
  value       = aws_bedrockagentcore_gateway.orders.gateway_url
}

output "ecr_repository_url" {
  description = "ECR repository for the agent image"
  value       = aws_ecr_repository.agent.repository_url
}
