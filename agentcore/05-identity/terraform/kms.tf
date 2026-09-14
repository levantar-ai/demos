# One customer-managed key for the demo's data at rest: the two exchange
# secrets, the exchange log groups and API access log, the Lambda environment
# variables and the agent's ECR repository. Nothing here is a signing key; the
# exchange pool signs with Cognito's own keys.
#
# The key policy lets IAM policies in this account grant use of the key (the
# root statement), and lets CloudWatch Logs use it for log groups in this
# account. Every other use, Secrets Manager, Lambda and ECR, is by a role in
# this account through its own IAM policy.
resource "aws_kms_key" "demo" {
  description             = "${local.name_prefix} data-at-rest key"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AccountAdministersTheKey"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      },
      {
        Sid       = "CloudWatchLogsEncryptsLogGroups"
        Effect    = "Allow"
        Principal = { Service = "logs.${var.aws_region}.amazonaws.com" }
        Action = [
          "kms:Encrypt*",
          "kms:Decrypt*",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:Describe*"
        ]
        Resource = "*"
        Condition = {
          ArnLike = {
            "kms:EncryptionContext:aws:logs:arn" = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:*"
          }
        }
      },
    ]
  })

  tags = {
    Project = "demos"
    Demo    = local.demo_slug
  }
}

resource "aws_kms_alias" "demo" {
  name          = "alias/${local.name_prefix}-data"
  target_key_id = aws_kms_key.demo.key_id
}
