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
    error_message = "policy_mode must be ENFORCE or LOG_ONLY."
  }
}
