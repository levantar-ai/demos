locals {
  # The issuer is the HTTP API's own endpoint. Referencing the API (not its
  # integration, which references the Lambda) keeps the dependency acyclic:
  # API -> Lambda (env) -> integration -> routes.
  exchange_issuer    = aws_apigatewayv2_api.exchange.api_endpoint
  orders_audience    = "brightwell-orders"
  orders_scope       = "orders/read"
  exchange_client_id = "brightwell-orders-agent" # the client the provider authenticates as
}

# The self-hosted RFC 8693 token-exchange service, the on-behalf-of target for
# AgentCore Identity. Cognito cannot be an exchange target, so this stands in
# for what a managed IdP (Entra, Auth0) would do. It is a token ISSUER, so it
# is treated as crown-jewel infrastructure: the signing key is KMS asymmetric
# and the Lambda role can only Sign with it, nothing else. Compromise of this
# code or its role is total issuer compromise; KMS stops key export, not
# arbitrary signing. In production you would use a managed IdP instead.

# --- Signing key: asymmetric, KMS-held, sign-only for the Lambda -------------
resource "aws_kms_key" "exchange" {
  description              = "${local.name_prefix} token-exchange ES256 signing key"
  key_usage                = "SIGN_VERIFY"
  customer_master_key_spec = "ECC_NIST_P256"
  # A short window so a torn-down demo does not leave a signer lingering.
  deletion_window_in_days = 7
}

resource "aws_kms_alias" "exchange" {
  name          = "alias/${local.name_prefix}-exchange"
  target_key_id = aws_kms_key.exchange.key_id
}

# --- Client secret for the /token endpoint (client_secret_basic) -------------
resource "random_password" "exchange_client_secret" {
  length  = 48
  special = false
}

resource "aws_secretsmanager_secret" "exchange_client" {
  name                    = "${local.name_prefix}-exchange-client"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "exchange_client" {
  secret_id     = aws_secretsmanager_secret.exchange_client.id
  secret_string = jsonencode({ client_secret = random_password.exchange_client_secret.result })
}

# --- Package the Lambda with its pinned deps (PyJWT + cryptography) -----------
# Built locally at apply time; CI has no AWS access and does not run this.
resource "null_resource" "exchange_build" {
  triggers = {
    handler = filemd5("${path.module}/../exchange/handler.py")
    reqs    = filemd5("${path.module}/../exchange/requirements.txt")
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
      cp "${path.module}/../exchange/handler.py" "$build/"
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

# --- Lambda role: Sign on the one key only, read the one secret, logs --------
resource "aws_iam_role" "exchange" {
  name = "${local.name_prefix}-exchange"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "exchange_logs" {
  role       = aws_iam_role.exchange.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "exchange" {
  name = "sign-and-read-secret"
  role = aws_iam_role.exchange.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Sign only, and only with ECDSA_SHA_256, on the one key. No key
        # administration, no grant creation, no other algorithm.
        Sid      = "SignOnly"
        Effect   = "Allow"
        Action   = ["kms:Sign", "kms:GetPublicKey"]
        Resource = aws_kms_key.exchange.arn
        Condition = {
          "ForAllValues:StringEquals" = { "kms:SigningAlgorithm" = ["ECDSA_SHA_256"] }
        }
      },
      {
        Sid      = "ReadClientSecret"
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = aws_secretsmanager_secret.exchange_client.arn
      },
    ]
  })
}

# --- The Lambda --------------------------------------------------------------
resource "aws_lambda_function" "exchange" {
  function_name    = "${local.name_prefix}-exchange"
  role             = aws_iam_role.exchange.arn
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.exchange.output_path
  source_code_hash = data.archive_file.exchange.output_base64sha256
  timeout          = 10
  memory_size      = 256
  environment {
    variables = {
      COGNITO_ISSUER          = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.agents.id}"
      COGNITO_JWKS_URL        = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.agents.id}/.well-known/jwks.json"
      ALLOWED_CLIENT_IDS      = aws_cognito_user_pool_client.customers.id
      ISSUER_URL              = local.exchange_issuer
      ORDERS_AUDIENCE         = local.orders_audience
      ORDERS_SCOPE            = local.orders_scope
      KMS_KEY_ID              = aws_kms_key.exchange.arn # the immutable key ARN, not an alias
      CLIENT_SECRET_ARN       = aws_secretsmanager_secret.exchange_client.arn
      EXCHANGE_CLIENT_ID      = local.exchange_client_id
      MAX_TTL_SECONDS         = "300"
      MIN_REMAINING_SECONDS   = "30"
      MAX_SUBJECT_AGE_SECONDS = "3600"
    }
  }
}

# --- HTTP API (TLS only) fronting the Lambda ---------------------------------
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
  for_each  = toset(["POST /token", "GET /.well-known/openid-configuration", "GET /.well-known/jwks.json"])
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
