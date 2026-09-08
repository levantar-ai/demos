# One Cognito pool with a public client for customers. They sign in with a
# password to get the access token the runtime and the gateway both check.
# The confidential agent client from post 02 is gone, the agent no longer
# mints its own token, it relays the customer's.

resource "aws_cognito_user_pool" "agents" {
  name = "${local.name_prefix}-pool"

  # Usernames are Brightwell's customer ids, so Brightwell creates the
  # accounts. Cognito's default allows self sign-up, which would let anyone
  # with the public client id register a customer id before its owner.
  admin_create_user_config {
    allow_admin_create_user_only = true
  }

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

# The customers' client. Brightwell's customer ids are the usernames in the
# pool, so the access token's username claim is the customer id and the
# agent takes its caller from that rather than from the request body.
resource "aws_cognito_user_pool_client" "customers" {
  name         = "${local.name_prefix}-customers"
  user_pool_id = aws_cognito_user_pool.agents.id

  generate_secret     = false
  explicit_auth_flows = ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
}
