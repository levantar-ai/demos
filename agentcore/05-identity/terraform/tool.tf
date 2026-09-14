# The Lambda the gateway exposes as an MCP tool.

# The whole tool directory, so orders.csv ships alongside the handler.
data "archive_file" "tool" {
  type        = "zip"
  source_dir  = "${path.module}/../tool"
  output_path = "${path.module}/.terraform/tool.zip"
  excludes    = ["__pycache__"]
}

resource "aws_iam_role" "tool" {
  name = "${local.name_prefix}-tool"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "lambda.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Project = "demos"
    Demo    = local.demo_slug
  }
}

resource "aws_iam_role_policy_attachment" "tool_logs" {
  role       = aws_iam_role.tool.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "tool_tracing" {
  name = "tracing"
  role = aws_iam_role.tool.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
      Resource = "*"
    }]
  })
}

resource "aws_lambda_function" "tool" {
  # checkov:skip=CKV_AWS_117:The tool reads a CSV packaged with it and calls nothing; a VPC would isolate nothing
  # checkov:skip=CKV_AWS_116:The gateway invokes the tool synchronously; a dead-letter queue applies to asynchronous invocation only
  # checkov:skip=CKV_AWS_272:Code signing is not adopted for a teaching stack
  # checkov:skip=CKV_AWS_173:The tool has no environment variables
  #ts:skip=AC_AWS_0486 The tool reads a CSV packaged with it and calls nothing; a VPC would isolate nothing
  #ts:skip=AC_AWS_0485 tracing_config mode Active is set below; the rule does not read that block
  function_name                  = "${local.name_prefix}-orders"
  role                           = aws_iam_role.tool.arn
  runtime                        = "python3.12"
  handler                        = "orders.handler"
  filename                       = data.archive_file.tool.output_path
  source_code_hash               = data.archive_file.tool.output_base64sha256
  reserved_concurrent_executions = 20
  tracing_config {
    mode = "Active"
  }

  tags = {
    Project = "demos"
    Demo    = local.demo_slug
  }
}
