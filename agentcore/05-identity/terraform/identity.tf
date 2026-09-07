# Outbound auth. AgentCore Identity holds the agent's client credentials in
# its token vault and exchanges them for a gateway token when the agent asks,
# so the agent's execution role no longer reads a secret and the agent's
# code no longer holds one.
#
# The credentials are write-only arguments, sent to the service but never
# persisted in Terraform state. Bump the version to push new values.

resource "aws_bedrockagentcore_oauth2_credential_provider" "gateway" {
  name                       = "${local.name_prefix}-gateway"
  credential_provider_vendor = "CustomOauth2"

  oauth2_provider_config {
    custom_oauth2_provider_config {
      client_id_wo                  = aws_cognito_user_pool_client.agent.id
      client_secret_wo              = aws_cognito_user_pool_client.agent.client_secret
      client_credentials_wo_version = 1

      oauth_discovery {
        discovery_url = local.discovery_url
      }
    }
  }

  # The discovery document only lists a token endpoint once the pool has a
  # domain, and the provider fetches it at creation.
  depends_on = [aws_cognito_user_pool_domain.agents]

  tags = {
    Project = "demos"
    Demo    = local.demo_slug
  }
}
