terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {}
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  description = "AWS region for account-level resources (IAM is global)"
  type        = string
  default     = "eu-west-2"
}

variable "agentcore_region" {
  description = "Region where AgentCore demo resources are deployed"
  type        = string
  default     = "us-east-1"
}

variable "github_org" {
  description = "GitHub organization/username"
  type        = string
  default     = "levantar-ai"
}

variable "github_repo" {
  description = "GitHub repository name"
  type        = string
  default     = "demos"
}

variable "terraform_state_bucket" {
  description = "S3 bucket for Terraform state"
  type        = string
  default     = "opptora-state"
}

data "aws_caller_identity" "current" {}

# Reference the existing OIDC provider (created by ideation)
data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}
