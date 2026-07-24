# Machine-to-machine auth for the gateway: the agent exchanges client
# credentials for a JWT which the gateway's authorizer validates.

resource "aws_cognito_user_pool" "gateway" {
  name = "${local.name_prefix}-auth"

  tags = {
    Project = "demos"
    Demo    = local.demo_slug
  }
}

resource "aws_cognito_user_pool_domain" "gateway" {
  domain       = "${local.name_prefix}-${data.aws_caller_identity.current.account_id}"
  user_pool_id = aws_cognito_user_pool.gateway.id
}

resource "aws_cognito_resource_server" "gateway" {
  identifier   = "demos-gateway"
  name         = "${local.name_prefix}-tools"
  user_pool_id = aws_cognito_user_pool.gateway.id

  scope {
    scope_name        = "invoke"
    scope_description = "Invoke gateway tools"
  }
}

resource "aws_cognito_user_pool_client" "agent" {
  name         = "${local.name_prefix}-agent"
  user_pool_id = aws_cognito_user_pool.gateway.id

  generate_secret                      = true
  allowed_oauth_flows                  = ["client_credentials"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_scopes                 = [local.scope]
  supported_identity_providers         = ["COGNITO"]

  depends_on = [aws_cognito_resource_server.gateway]
}

locals {
  token_url     = "https://${aws_cognito_user_pool_domain.gateway.domain}.auth.${var.aws_region}.amazoncognito.com/oauth2/token"
  discovery_url = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.gateway.id}/.well-known/openid-configuration"
}
