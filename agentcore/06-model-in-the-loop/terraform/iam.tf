# Execution role assumed by the AgentCore Runtime. The trust is bound to a
# runtime in this account whose ARN starts with this demo's runtime name;
# the ARN itself is not known until the runtime exists, so a name pattern
# is as tight as the trust can be written.

resource "aws_iam_role" "runtime" {
  name = "${local.name_prefix}-runtime"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "bedrock-agentcore.amazonaws.com"
        }
        Action = "sts:AssumeRole"
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
          ArnLike = {
            "aws:SourceArn" = "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:runtime/${local.runtime_name}-*"
          }
        }
      }
    ]
  })

  tags = {
    Project = "demos"
    Demo    = local.demo_slug
  }
}

resource "aws_iam_role_policy" "runtime" {
  name = "runtime-permissions"
  role = aws_iam_role.runtime.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "PullAgentImage"
        Effect = "Allow"
        Action = [
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:BatchCheckLayerAvailability"
        ]
        Resource = aws_ecr_repository.agent.arn
      },
      {
        Sid      = "EcrAuth"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      # The repository is encrypted with the demo key, but ECR decrypts through
      # the grants it holds on that key, so the puller needs the ECR actions
      # above and no KMS permission of its own (confirmed by a fresh pull).
      {
        Sid    = "Logs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        # The service creates this runtime's groups under its own name, so
        # the role is scoped to that prefix rather than to every AgentCore
        # group in the account.
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/${local.runtime_name}-*"
      },
      {
        Sid    = "Tracing"
        Effect = "Allow"
        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords"
        ]
        Resource = "*"
      },
      {
        Sid      = "Metrics"
        Effect   = "Allow"
        Action   = ["cloudwatch:PutMetricData"]
        Resource = "*"
        Condition = {
          StringEquals = {
            "cloudwatch:namespace" = "bedrock-agentcore"
          }
        }
      },
      {
        Sid    = "CodeInterpreter"
        Effect = "Allow"
        Action = [
          "bedrock-agentcore:StartCodeInterpreterSession",
          "bedrock-agentcore:InvokeCodeInterpreter",
          "bedrock-agentcore:StopCodeInterpreterSession"
        ]
        Resource = aws_bedrockagentcore_code_interpreter.sandbox.code_interpreter_arn
      },
      {
        # The model. Invocation goes to the cross-region inference profile,
        # which routes to the foundation model in one of its regions, and
        # Bedrock evaluates both ARNs, so this statement names the profile
        # and the next names the exact model in each region the profile
        # reports it routes to. Nothing else in Bedrock is callable from
        # this role.
        Sid    = "InvokeTheInferenceProfile"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = local.inference_profile_arn
      },
      {
        # The condition means the model can be reached only through that
        # profile, never by naming a regional model directly.
        Sid    = "InvokeTheModelThroughTheProfile"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = data.aws_bedrock_inference_profile.model.models[*].model_arn
        Condition = {
          StringEquals = {
            "bedrock:InferenceProfileArn" = local.inference_profile_arn
          }
        }
      },
      {
        # The session manager reads the session back (ListEvents, GetEvent),
        # appends each turn (CreateEvent) and retrieves the customer's
        # long-term records (RetrieveMemoryRecords). Nothing that deletes.
        Sid    = "Memory"
        Effect = "Allow"
        Action = [
          "bedrock-agentcore:CreateEvent",
          "bedrock-agentcore:GetEvent",
          "bedrock-agentcore:ListEvents",
          "bedrock-agentcore:RetrieveMemoryRecords"
        ]
        Resource = aws_bedrockagentcore_memory.agent.arn
      },
      {
        # The on-behalf-of chain: exchange the customer's JWT for a workload
        # access token for this agent's workload identity, then request the
        # resource token from this one credential provider. Scoped to the
        # exact resources (their ARN forms were confirmed by the live run,
        # see artifacts/README.md), with the parent directory and vault the
        # actions are authorised against. No other workload identity or
        # provider in the account is reachable from this role.
        Sid    = "OnBehalfOfExchange"
        Effect = "Allow"
        Action = [
          "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
          "bedrock-agentcore:GetResourceOauth2Token"
        ]
        Resource = [
          "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:workload-identity-directory/default",
          aws_bedrockagentcore_workload_identity.agent.workload_identity_arn,
          "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:token-vault/default",
          local.obo_provider_arn
        ]
      },
      {
        # GetResourceOauth2Token reads the credential provider's client secret
        # in the caller's context. The exact ARN of the secret AgentCore
        # Identity manages for the provider comes from the provider itself, so
        # the runtime role can read that one secret and no other.
        Sid      = "ReadOboProviderSecret"
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = local.obo_provider_secret_arn
      },
    ]
  })
}
