output "runtime_arn" {
  description = "ARN of the deployed AgentCore runtime"
  value       = aws_bedrockagentcore_agent_runtime.agent.agent_runtime_arn
}

# With a JWT authorizer the runtime is called over plain HTTPS with a bearer
# token rather than through the SigV4-signed CLI, so the URL is an output.
output "invoke_url" {
  description = "HTTPS endpoint to POST invocations to, with a customer's bearer token"
  value       = "https://bedrock-agentcore.${var.aws_region}.amazonaws.com/runtimes/${urlencode(aws_bedrockagentcore_agent_runtime.agent.agent_runtime_arn)}/invocations?qualifier=DEFAULT"
}

output "aws_region" {
  description = "Region the stack is deployed in, for the CLI commands"
  value       = var.aws_region
}

output "user_pool_id" {
  description = "Cognito pool the customer accounts live in"
  value       = aws_cognito_user_pool.agents.id
}

output "customers_client_id" {
  description = "App client customers sign in with to get a token"
  value       = aws_cognito_user_pool_client.customers.id
}

output "workload_identity_arn" {
  description = "Workload identity AgentCore created for the runtime"
  value       = one(aws_bedrockagentcore_agent_runtime.agent.workload_identity_details).workload_identity_arn
}

output "code_interpreter_id" {
  description = "Id of the code interpreter sandbox"
  value       = aws_bedrockagentcore_code_interpreter.sandbox.code_interpreter_id
}

output "ecr_repository_url" {
  description = "ECR repository for the agent image"
  value       = aws_ecr_repository.agent.repository_url
}
