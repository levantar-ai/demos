# Post 07. The runtime sends its own logs and spans once the container runs
# under ADOT (agent/Dockerfile). The gateway and the memory do not: AgentCore
# leaves their log and trace destinations to the account, so each is wired
# here as a CloudWatch Logs delivery, the resource as the source and a log
# group or X-Ray as the destination.
#
# Their spans join the agent's trace, so one turn reads as one tree: the
# runtime's invocation, the model calls, the gateway's tool call and the
# memory's reads and writes.
#
# Spans reach CloudWatch through Transaction Search, which is an account
# setting, enabled once per account and Region and not owned by this demo
# (README.md, "Transaction Search").

locals {
  # The two resources that leave their logs and traces to the account.
  observed = {
    gateway = aws_bedrockagentcore_gateway.orders.gateway_arn
    memory  = aws_bedrockagentcore_memory.agent.arn
  }
  # The /aws/vendedlogs/ prefix is the one CloudWatch Logs grants delivery to
  # without a resource policy per group.
  vended_log_group = "/aws/vendedlogs/bedrock-agentcore/${local.name_prefix}"
  # The service names the runtime's group after the runtime and its endpoint.
  runtime_log_group = "/aws/bedrock-agentcore/runtimes/${aws_bedrockagentcore_agent_runtime.agent.agent_runtime_id}-DEFAULT"
}

# The gateway's application logs carry each request and response, the
# customer's orders among them, so the groups are encrypted with the demo key
# and kept for a week, as the demo's other logs are.
resource "aws_cloudwatch_log_group" "observed" {
  # checkov:skip=CKV_AWS_338:Seven days is the retention for a teaching stack that is destroyed after the post
  for_each          = local.observed
  name              = "${local.vended_log_group}/${each.key}"
  retention_in_days = 7
  kms_key_id        = aws_kms_key.demo.arn

  tags = {
    Project = "demos"
    Demo    = local.demo_slug
  }
}

resource "aws_cloudwatch_log_delivery_source" "logs" {
  for_each     = local.observed
  name         = "${local.name_prefix}-${each.key}-logs"
  log_type     = "APPLICATION_LOGS"
  resource_arn = each.value
}

resource "aws_cloudwatch_log_delivery_source" "traces" {
  for_each     = local.observed
  name         = "${local.name_prefix}-${each.key}-traces"
  log_type     = "TRACES"
  resource_arn = each.value
}

resource "aws_cloudwatch_log_delivery_destination" "logs" {
  for_each = local.observed
  name     = "${local.name_prefix}-${each.key}-logs"

  delivery_destination_configuration {
    destination_resource_arn = aws_cloudwatch_log_group.observed[each.key].arn
  }
}

# X-Ray takes no resource of its own: the spans go to the account's trace
# store, which Transaction Search writes to the aws/spans log group.
resource "aws_cloudwatch_log_delivery_destination" "traces" {
  name                      = "${local.name_prefix}-traces"
  delivery_destination_type = "XRAY"
}

resource "aws_cloudwatch_log_delivery" "logs" {
  for_each                 = local.observed
  delivery_source_name     = aws_cloudwatch_log_delivery_source.logs[each.key].name
  delivery_destination_arn = aws_cloudwatch_log_delivery_destination.logs[each.key].arn
}

resource "aws_cloudwatch_log_delivery" "traces" {
  for_each                 = local.observed
  delivery_source_name     = aws_cloudwatch_log_delivery_source.traces[each.key].name
  delivery_destination_arn = aws_cloudwatch_log_delivery_destination.traces.arn
}

# The runtime's own group holds what the agent's spans record: the system
# prompt, the customer's question, every model reply and every tool result,
# the customer's orders included. The service creates it with the runtime,
# named after the runtime's id, with no expiry and no customer key, so
# Terraform cannot create it first. This gives it the demo key and the same
# week as the other groups once the runtime exists.
resource "null_resource" "runtime_log_group" {
  triggers = {
    log_group = local.runtime_log_group
    key       = aws_kms_key.demo.arn
  }
  provisioner "local-exec" {
    interpreter = ["bash", "-c"]
    command     = <<-EOT
      set -euo pipefail
      aws logs put-retention-policy --region ${var.aws_region} \
        --log-group-name "${local.runtime_log_group}" --retention-in-days 7
      aws logs associate-kms-key --region ${var.aws_region} \
        --log-group-name "${local.runtime_log_group}" --kms-key-id "${aws_kms_key.demo.arn}"
    EOT
  }
}
