locals {
  # The issuer URL the OBO credential provider is pointed at is the HTTP
  # API's own endpoint. Referencing the API (not its integration, which
  # references the Lambda) keeps the dependency acyclic.
  exchange_issuer    = aws_apigatewayv2_api.exchange.api_endpoint
  orders_scope       = "orders/read"
  exchange_client_id = "brightwell-orders-agent" # the front door's OAuth client, which the provider authenticates as
  service_user       = "orders-agent"            # the exchange pool user the flow runs as
  exchange_functions = ["exchange", "define", "create", "verify", "pretoken"]
}

# The on-behalf-of target for AgentCore Identity, built the way AWS's
# sample-cognito-oauth2-token-exchange builds it: Cognito's token endpoint does
# not offer the RFC 8693 grant, so a small front door (one Lambda behind an
# HTTP API) implements the grant and a SECOND Cognito user pool, the exchange
# pool, mints the token through its custom authentication flow. The front door
# signs nothing and holds no key. The pool's four triggers verify the customer's
# token and decide the claims; Cognito signs with its own keys and publishes
# its own discovery document and JWKS, which the gateway trusts.
#
# On top of the sample: the pool's app client is confidential (so the flow
# cannot be run against Cognito directly without a second secret that only
# the front door's role reads), the
# pre-token trigger adds an aud claim (the app client id, one client per
# downstream, which the gateway enforces with allowed_audience), the access
# token lives five minutes, and every trigger fails closed.
#
# Still a TEACHING component. In production the exchange belongs to a managed
# IdP with a supported on-behalf-of integration.

# --- The exchange pool, its confidential app client and its service user -----
resource "aws_cognito_user_pool" "exchange" {
  name = "${local.name_prefix}-exchange-pool"
  # Access-token customisation from the pre-token trigger needs Essentials.
  user_pool_tier      = "ESSENTIALS"
  mfa_configuration   = "OFF"
  deletion_protection = "INACTIVE"

  # The only user is the service user, created by Terraform below.
  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  lambda_config {
    define_auth_challenge          = aws_lambda_function.triggers["define"].arn
    create_auth_challenge          = aws_lambda_function.triggers["create"].arn
    verify_auth_challenge_response = aws_lambda_function.triggers["verify"].arn
    pre_token_generation_config {
      lambda_arn     = aws_lambda_function.triggers["pretoken"].arn
      lambda_version = "V2_0" # access-token claims and scopes
    }
  }

  tags = {
    Project = "demos"
    Demo    = local.demo_slug
  }
}

# One app client per downstream. Its id is the minted token's client_id and,
# because the pre-token trigger adds it, its aud. Confidential, custom auth
# only: no password, SRP or refresh flow can produce a token from this pool.
resource "aws_cognito_user_pool_client" "orders" {
  name                          = "orders"
  user_pool_id                  = aws_cognito_user_pool.exchange.id
  generate_secret               = true
  explicit_auth_flows           = ["ALLOW_CUSTOM_AUTH"]
  prevent_user_existence_errors = "ENABLED"

  # Five minutes is Cognito's minimum. The front door never returns the
  # refresh token, and the pre-token trigger refuses a refresh (Cognito was
  # seen to process a refresh attempt on this custom-auth-only client, so the
  # trigger is the control, not this list); sixty minutes is the minimum.
  access_token_validity  = 5
  id_token_validity      = 5
  refresh_token_validity = 60
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "minutes"
  }
}

# The service user the exchange runs as. The minted token's sub and username
# are this user's; the customer travels in the customer_id claim. The password
# is random and unusable: no client in this pool allows a password flow. It is
# set as permanent so the user is CONFIRMED and can complete CUSTOM_AUTH.
resource "random_password" "service_user" {
  length  = 32
  special = true
}

resource "aws_cognito_user" "orders_agent" {
  user_pool_id   = aws_cognito_user_pool.exchange.id
  username       = local.service_user
  password       = random_password.service_user.result
  message_action = "SUPPRESS"
}

# The pool references the triggers, so the triggers cannot be given the pool's
# ids as environment at deploy time. They read them from this parameter, which
# is written once the pool and client exist. Only the exchange functions may
# read it.
resource "aws_ssm_parameter" "exchange_config" {
  name = "/${local.name_prefix}/exchange"
  type = "String"
  value = jsonencode({
    pool_id      = aws_cognito_user_pool.exchange.id
    client_id    = aws_cognito_user_pool_client.orders.id
    service_user = local.service_user
  })
}

# --- Secrets: the front door's client secret, and the app client's --------------
resource "random_password" "exchange_client_secret" {
  length  = 48
  special = false
}

# What AgentCore Identity's provider authenticates to /token with.
resource "aws_secretsmanager_secret" "exchange_client" {
  name                    = "${local.name_prefix}-exchange-client"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "exchange_client" {
  secret_id     = aws_secretsmanager_secret.exchange_client.id
  secret_string = jsonencode({ client_secret = random_password.exchange_client_secret.result })
}

# What the front door computes SECRET_HASH with. Kept apart from the secret
# above: holding the provider's credential does not let you call Cognito.
resource "aws_secretsmanager_secret" "orders_client" {
  name                    = "${local.name_prefix}-exchange-orders-client"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "orders_client" {
  secret_id     = aws_secretsmanager_secret.orders_client.id
  secret_string = jsonencode({ client_secret = aws_cognito_user_pool_client.orders.client_secret })
}

# --- One package for all five functions (PyJWT + cryptography) -----------------
# Built locally at apply time; CI has no AWS access and does not run this.
resource "null_resource" "exchange_build" {
  triggers = {
    handler  = filemd5("${path.module}/../exchange/handler.py")
    triggers = filemd5("${path.module}/../exchange/triggers.py")
    subject  = filemd5("${path.module}/../exchange/subject.py")
    reqs     = filemd5("${path.module}/../exchange/requirements.txt")
  }
  provisioner "local-exec" {
    interpreter = ["bash", "-c"]
    command     = <<-EOT
      set -euo pipefail
      build="${path.module}/.build/exchange"
      rm -rf "$build" && mkdir -p "$build"
      python3 -m pip install -r "${path.module}/../exchange/requirements.txt" \
        --platform manylinux2014_x86_64 --python-version 3.12 \
        --implementation cp --only-binary=:all: --target "$build" --quiet
      cp "${path.module}/../exchange/handler.py" "${path.module}/../exchange/triggers.py" \
         "${path.module}/../exchange/subject.py" "$build/"
      find "$build" -type d -name "__pycache__" -prune -exec rm -rf {} +
    EOT
  }
}

data "archive_file" "exchange" {
  type        = "zip"
  source_dir  = "${path.module}/.build/exchange"
  output_path = "${path.module}/.build/exchange.zip"
  depends_on  = [null_resource.exchange_build]
}

# --- Log groups first, so the roles need no CreateLogGroup ----------------------
resource "aws_cloudwatch_log_group" "exchange" {
  for_each          = toset(local.exchange_functions)
  name              = each.key == "exchange" ? "/aws/lambda/${local.name_prefix}-exchange" : "/aws/lambda/${local.name_prefix}-exchange-${each.key}"
  retention_in_days = 7
}

# --- Roles: the front door's, and one shared by the four triggers -----------------
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "exchange" {
  name               = "${local.name_prefix}-exchange"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role" "exchange_triggers" {
  name               = "${local.name_prefix}-exchange-triggers"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "exchange" {
  name = "run-the-exchange-flow"
  role = aws_iam_role.exchange.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # The two admin calls that drive CUSTOM_AUTH, on the exchange pool
        # only. Cognito IAM cannot narrow these to one user or app client;
        # the triggers' guards are the compensating control.
        Sid    = "RunCustomAuth"
        Effect = "Allow"
        Action = [
          "cognito-idp:AdminInitiateAuth",
          "cognito-idp:AdminRespondToAuthChallenge"
        ]
        Resource = aws_cognito_user_pool.exchange.arn
      },
      {
        Sid    = "ReadItsTwoSecrets"
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue"]
        Resource = [
          aws_secretsmanager_secret.exchange_client.arn,
          aws_secretsmanager_secret.orders_client.arn,
        ]
      },
      {
        Sid      = "ReadPoolConfig"
        Effect   = "Allow"
        Action   = ["ssm:GetParameter"]
        Resource = aws_ssm_parameter.exchange_config.arn
      },
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.exchange["exchange"].arn}:*"
      },
    ]
  })
}

resource "aws_iam_role_policy" "exchange_triggers" {
  name = "verify-and-mint"
  role = aws_iam_role.exchange_triggers.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # The triggers need no Cognito permissions at all; Cognito calls them.
        # One role for the four is a demo simplification: a compromised
        # trigger could write to a sibling's log group, nothing more.
        Sid      = "ReadPoolConfig"
        Effect   = "Allow"
        Action   = ["ssm:GetParameter"]
        Resource = aws_ssm_parameter.exchange_config.arn
      },
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = [for k in ["define", "create", "verify", "pretoken"] : "${aws_cloudwatch_log_group.exchange[k].arn}:*"]
      },
    ]
  })
}

# --- The five functions ----------------------------------------------------------
# The triggers are a separate resource from the front door: the pool depends
# on the triggers, and the front door depends on the pool (for its JWKS URL
# and app-client secret), so one for_each resource would be a cycle.
locals {
  trigger_handlers = {
    define   = "triggers.define"
    create   = "triggers.create"
    verify   = "triggers.verify"
    pretoken = "triggers.pretoken"
  }
  # What every function needs to verify the customer's token.
  subject_env = {
    COGNITO_ISSUER            = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.agents.id}"
    COGNITO_JWKS_URL          = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.agents.id}/.well-known/jwks.json"
    ALLOWED_CLIENT_IDS        = aws_cognito_user_pool_client.customers.id
    MAX_SUBJECT_AGE_SECONDS   = "3600"
    ORDERS_SCOPE              = local.orders_scope
    EXCHANGE_CONFIG_PARAMETER = "/${local.name_prefix}/exchange" # the name, not the resource: no cycle
  }
}

resource "aws_lambda_function" "triggers" {
  for_each         = local.trigger_handlers
  function_name    = "${local.name_prefix}-exchange-${each.key}"
  role             = aws_iam_role.exchange_triggers.arn
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  handler          = each.value
  filename         = data.archive_file.exchange.output_path
  source_code_hash = data.archive_file.exchange.output_base64sha256
  # Cognito waits five seconds for a trigger; the JWKS fetch is the slow part.
  timeout     = 5
  memory_size = 512
  environment {
    variables = local.subject_env
  }
  depends_on = [aws_cloudwatch_log_group.exchange]
}

resource "aws_lambda_function" "exchange" {
  function_name    = "${local.name_prefix}-exchange"
  role             = aws_iam_role.exchange.arn
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.exchange.output_path
  source_code_hash = data.archive_file.exchange.output_base64sha256
  timeout          = 10
  memory_size      = 512
  environment {
    variables = merge(local.subject_env, {
      ISSUER_URL               = local.exchange_issuer
      EXCHANGE_JWKS_URL        = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.exchange.id}/.well-known/jwks.json"
      ORDERS_CLIENT_SECRET_ARN = aws_secretsmanager_secret.orders_client.arn
      CLIENT_SECRET_ARN        = aws_secretsmanager_secret.exchange_client.arn
      EXCHANGE_CLIENT_ID       = local.exchange_client_id
    })
  }
  depends_on = [aws_cloudwatch_log_group.exchange]
}

# Cognito may invoke the four triggers, from this pool and this account only.
resource "aws_lambda_permission" "exchange_triggers" {
  for_each       = local.trigger_handlers
  statement_id   = "AllowInvokeFromExchangePool"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.triggers[each.key].function_name
  principal      = "cognito-idp.amazonaws.com"
  source_arn     = aws_cognito_user_pool.exchange.arn
  source_account = data.aws_caller_identity.current.account_id
}

# --- HTTP API (TLS only) fronting the front door ---------------------------------
resource "aws_apigatewayv2_api" "exchange" {
  name          = "${local.name_prefix}-exchange"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "exchange" {
  api_id                 = aws_apigatewayv2_api.exchange.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.exchange.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "exchange" {
  for_each  = toset(["POST /token", "GET /authorize", "GET /.well-known/openid-configuration"])
  api_id    = aws_apigatewayv2_api.exchange.id
  route_key = each.value
  target    = "integrations/${aws_apigatewayv2_integration.exchange.id}"
}

resource "aws_apigatewayv2_stage" "exchange" {
  api_id      = aws_apigatewayv2_api.exchange.id
  name        = "$default"
  auto_deploy = true
  default_route_settings {
    throttling_burst_limit = 20
    throttling_rate_limit  = 20
  }
}

resource "aws_lambda_permission" "exchange" {
  statement_id  = "AllowInvokeFromHttpApi"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.exchange.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.exchange.execution_arn}/*/*"
}
