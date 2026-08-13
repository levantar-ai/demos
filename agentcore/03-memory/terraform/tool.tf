# The Lambda the gateway exposes as an MCP tool.

data "archive_file" "tool" {
  type        = "zip"
  source_file = "${path.module}/../tool/lookup_order.py"
  output_path = "${path.module}/.terraform/tool.zip"
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

resource "aws_lambda_function" "tool" {
  function_name    = "${local.name_prefix}-lookup-order"
  role             = aws_iam_role.tool.arn
  runtime          = "python3.12"
  handler          = "lookup_order.handler"
  filename         = data.archive_file.tool.output_path
  source_code_hash = data.archive_file.tool.output_base64sha256

  tags = {
    Project = "demos"
    Demo    = local.demo_slug
  }
}
