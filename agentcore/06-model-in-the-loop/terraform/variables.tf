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
  description = "Bedrock inference profile the agent reasons with, Claude 4.5 family; the runtime role is scoped to it and to the models it routes to"
  type        = string
  default     = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
}

