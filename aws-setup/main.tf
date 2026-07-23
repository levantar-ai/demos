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

# GitHub OIDC provider — first one in this account (134570442530). If another
# repo later needs it, that repo should reference it with a data source.
resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1", "1c58a3a8518e8759bf075b76b750d4f2df264fcd"]

  tags = {
    Name      = "GitHub Actions OIDC"
    ManagedBy = "Terraform"
    Project   = "demos"
  }

  lifecycle {
    ignore_changes = [thumbprint_list]
  }
}
