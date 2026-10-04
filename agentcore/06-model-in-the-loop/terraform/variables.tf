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
  description = "Policy engine mode: ENFORCE denies; LOG_ONLY records the decision and lets the call through, for synthetic data in an isolated account only"
  type        = string
  default     = "ENFORCE"
  validation {
    condition     = contains(["ENFORCE", "LOG_ONLY"], var.policy_mode)
    error_message = "The policy_mode value must be ENFORCE or LOG_ONLY."
  }
}

variable "model_id" {
  description = "Bedrock model the agent reasons with, a cross-region inference profile id in the Claude 4.5 family"
  type        = string
  default     = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
}

variable "model_regions" {
  description = "Regions the inference profile may route to; the runtime role is allowed the foundation model in exactly these"
  type        = list(string)
  default     = ["us-east-1", "us-east-2", "us-west-2"]
}
