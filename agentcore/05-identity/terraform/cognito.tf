# One Cognito pool, two app clients. The agent is a confidential client with
# no human behind it and uses the client_credentials grant to reach the
# gateway, as post 02 set up. Customers are people, so they get a public
# client with no secret and sign in with a password to get the access token
# the runtime checks.

resource "aws_cognito_user_pool" "agents" {
  name = "${local.name_prefix}-pool"

  tags = {
    Project = "demos"
    Demo    = local.demo_slug
  }
}

# The token endpoint lives on this domain. The prefix must be unique among
# Cognito user pool domains in the Region, hence the account id suffix.
resource "aws_cognito_user_pool_domain" "agents" {
  domain       = "${local.name_prefix}-${data.aws_caller_identity.current.account_id}"
  user_pool_id = aws_cognito_user_pool.agents.id
}

# Declares the scope the agent asks for and the gateway can check.
resource "aws_cognito_resource_server" "orders" {
  identifier   = "orders-api"
  name         = "orders-api"
  user_pool_id = aws_cognito_user_pool.agents.id

  scope {
    scope_name        = "invoke"
    scope_description = "Invoke order tools through the gateway"
  }
}

# The agent's client. Its secret goes to the credential provider in
# identity.tf and nowhere else, the agent never reads it.
resource "aws_cognito_user_pool_client" "agent" {
  name         = "${local.name_prefix}-agent"
  user_pool_id = aws_cognito_user_pool.agents.id

  generate_secret                      = true
  allowed_oauth_flows                  = ["client_credentials"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_scopes                 = aws_cognito_resource_server.orders.scope_identifiers
  supported_identity_providers         = ["COGNITO"]
}

# The customers' client. Brightwell's customer ids are the usernames in the
# pool, so the access token's username claim is the customer id and the
# agent takes its caller from that rather than from the request body.
resource "aws_cognito_user_pool_client" "customers" {
  name         = "${local.name_prefix}-customers"
  user_pool_id = aws_cognito_user_pool.agents.id

  generate_secret     = false
  explicit_auth_flows = ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
}
