# Cognito issues the access tokens the gateway validates. This is the
# machine-to-machine shape: the agent is a confidential client with no
# human in the loop, so it uses the client_credentials grant.

resource "aws_cognito_user_pool" "agents" {
  name = "${local.name_prefix}-pool"

  tags = {
    Project = "demos"
    Demo    = local.demo_slug
  }
}

# The token endpoint lives on this domain. The prefix is globally unique
# across all of Cognito, hence the account id suffix.
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

resource "aws_cognito_user_pool_client" "agent" {
  name         = "${local.name_prefix}-agent"
  user_pool_id = aws_cognito_user_pool.agents.id

  generate_secret                      = true
  allowed_oauth_flows                  = ["client_credentials"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_scopes                 = aws_cognito_resource_server.orders.scope_identifiers
  supported_identity_providers         = ["COGNITO"]
}

# The client secret never reaches the runtime as configuration. It goes
# in Secrets Manager and the agent reads it with its execution role.
resource "aws_secretsmanager_secret" "agent_client" {
  name                    = "${local.name_prefix}-agent-client"
  recovery_window_in_days = 0

  tags = {
    Project = "demos"
    Demo    = local.demo_slug
  }
}

resource "aws_secretsmanager_secret_version" "agent_client" {
  secret_id = aws_secretsmanager_secret.agent_client.id

  secret_string = jsonencode({
    client_id     = aws_cognito_user_pool_client.agent.id
    client_secret = aws_cognito_user_pool_client.agent.client_secret
  })
}
