terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.18"
    }
  }

  # Key set at init time:
  #   terraform/demos/agentcore/01-first-agent/terraform.tfstate
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

locals {
  # Namespacing: every AWS resource this demo creates carries this prefix so
  # all demos in the repo can coexist in one account.
  demo_slug   = "01-first-agent"
  name_prefix = "demos-agentcore-${local.demo_slug}"
  # AgentCore runtime names only allow [a-zA-Z0-9_]
  runtime_name = "demos_agentcore_01_first_agent"
  ecr_repo     = "demos/agentcore/${local.demo_slug}"
}
