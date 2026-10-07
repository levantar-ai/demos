variable "aws_region" {
  description = "AWS region (AgentCore availability)"
  type        = string
  default     = "us-east-1"
}

variable "image_tag" {
  description = "Tag of the agent container image to deploy (CI passes the git SHA; tags are immutable)"
  type        = string
}


variable "model_id" {
  description = "Bedrock system cross-region inference profile the agent reasons with, Claude 4.5 family; the runtime role is scoped to it and to the models it routes to"
  type        = string
  default     = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

  # The role's model statement is built from what the inference profile data
  # source reports for a system cross-region profile; that is the shape this
  # was built and tested with, so only that shape is accepted.
  validation {
    condition     = can(regex("^(us|eu|apac|global|us-gov)\\.anthropic\\.claude-(sonnet|haiku|opus)-4-5", var.model_id))
    error_message = "model_id must be a system cross-region inference profile for a Claude 4.5 model, such as us.anthropic.claude-sonnet-4-5-20250929-v1:0."
  }
}

