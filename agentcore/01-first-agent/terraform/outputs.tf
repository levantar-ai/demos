output "runtime_arn" {
  description = "ARN of the deployed AgentCore runtime"
  value       = aws_bedrockagentcore_agent_runtime.agent.agent_runtime_arn
}

output "ecr_repository_url" {
  description = "ECR repository for the agent image"
  value       = aws_ecr_repository.agent.repository_url
}

output "runtime_role_arn" {
  description = "Execution role assumed by the runtime"
  value       = aws_iam_role.runtime.arn
}
