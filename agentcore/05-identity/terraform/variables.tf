variable "aws_region" {
  description = "AWS region (AgentCore availability)"
  type        = string
  default     = "us-east-1"
}

variable "image_tag" {
  description = "Tag of the agent container image to deploy (CI passes the git SHA; tags are immutable)"
  type        = string
}

variable "policy_mode" {
  description = "Policy engine mode: LOG_ONLY to validate traces, ENFORCE to deny"
  type        = string
  default     = "ENFORCE"
}
