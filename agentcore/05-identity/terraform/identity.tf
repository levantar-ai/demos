# AgentCore Identity: the OAuth2 credential provider that performs the
# on-behalf-of exchange. The hashicorp/aws provider's
# aws_bedrockagentcore_oauth2_credential_provider (as of 6.64 / main) does not
# model on_behalf_of_token_exchange_config, so this is created through Cloud
# Control against the native CloudFormation type, which does.
#
# GrantType TOKEN_EXCHANGE (RFC 8693); ActorTokenContent NONE, so the exchange
# authenticates only by the client secret and asserts no workload actor. The
# provider points at the self-hosted exchange service's discovery URL; the
# client secret (client_secret_basic) is the same value the exchange Lambda
# validates from Secrets Manager.
resource "aws_cloudcontrolapi_resource" "obo_provider" {
  type_name = "AWS::BedrockAgentCore::OAuth2CredentialProvider"

  desired_state = jsonencode({
    Name                     = local.obo_provider_name
    CredentialProviderVendor = "CustomOauth2"
    Oauth2ProviderConfigInput = {
      CustomOauth2ProviderConfig = {
        OauthDiscovery = {
          DiscoveryUrl = "${local.exchange_issuer}/.well-known/openid-configuration"
        }
        ClientId                   = local.exchange_client_id
        ClientSecret               = random_password.exchange_client_secret.result
        ClientAuthenticationMethod = "CLIENT_SECRET_BASIC"
        OnBehalfOfTokenExchangeConfig = {
          GrantType                    = "TOKEN_EXCHANGE"
          TokenExchangeGrantTypeConfig = { ActorTokenContent = "NONE" }
        }
      }
    }
  })

  # The exchange service must be serving its discovery document before the
  # provider is created, in case AgentCore validates the discovery URL.
  depends_on = [
    aws_apigatewayv2_stage.exchange,
    aws_lambda_permission.exchange,
    aws_apigatewayv2_route.exchange,
  ]
}

locals {
  obo_provider_name = "demos_agentcore_05_obo"

  # The provider reports its own ARN and the ARN of the client secret AgentCore
  # Identity manages for it, so the runtime role can be scoped to exactly those.
  obo_provider_props      = jsondecode(aws_cloudcontrolapi_resource.obo_provider.properties)
  obo_provider_arn        = local.obo_provider_props.CredentialProviderArn
  obo_provider_secret_arn = local.obo_provider_props.ClientSecretArn.SecretArn
}

# An explicit workload identity for the agent, so its name is known at plan
# time (a runtime's auto-created one has an undocumented suffix, and a resource
# cannot reference its own output in its own env). The agent passes this name
# to get_workload_access_token_for_jwt; the runtime role is authorised for it.
# The live run confirmed the runtime may present this explicit workload
# identity to GetWorkloadAccessTokenForJWT rather than its own auto-created
# one (artifacts/README.md).
resource "aws_bedrockagentcore_workload_identity" "agent" {
  name = "demos_agentcore_05_agent"
}
