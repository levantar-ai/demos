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

output "runtime_auto_workload_identity_arn" {
  description = "Workload identity AgentCore auto-created for the runtime (not the one the OBO chain uses)"
  value       = one(aws_bedrockagentcore_agent_runtime.agent.workload_identity_details).workload_identity_arn
}

output "agent_workload_identity_arn" {
  description = "The explicit workload identity the agent presents in the on-behalf-of chain"
  value       = aws_bedrockagentcore_workload_identity.agent.workload_identity_arn
}

output "code_interpreter_id" {
  description = "Id of the code interpreter sandbox"
  value       = aws_bedrockagentcore_code_interpreter.sandbox.code_interpreter_id
}

output "ecr_repository_url" {
  description = "ECR repository for the agent image"
  value       = aws_ecr_repository.agent.repository_url
}

output "exchange_issuer" {
  description = "URL of the token-exchange front door (the OBO target's token endpoint lives here)"
  value       = local.exchange_issuer
}

output "exchange_pool_id" {
  description = "The exchange pool, the Cognito user pool that mints the on-behalf-of token"
  value       = aws_cognito_user_pool.exchange.id
}

output "orders_client_id" {
  description = "The exchange pool's orders app client: the minted token's client_id and aud"
  value       = aws_cognito_user_pool_client.orders.id
}

output "obo_provider_name" {
  description = "AgentCore Identity OAuth2 credential provider that performs the exchange"
  value       = local.obo_provider_name
}

output "agent_workload_name" {
  description = "Workload identity name the agent presents for the on-behalf-of exchange"
  value       = aws_bedrockagentcore_workload_identity.agent.name
}
