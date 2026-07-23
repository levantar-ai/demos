variable "aws_region" {
  description = "AWS region (AgentCore availability)"
  type        = string
  default     = "us-east-1"
}

variable "image_tag" {
  description = "Tag of the agent container image to deploy (set by CI to the git SHA)"
  type        = string
  default     = "latest"
}
