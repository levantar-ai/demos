terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.18"
    }
  }

  # Key set at init time:
  #   terraform/demos/agentcore/03-memory/terraform.tfstate
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

locals {
  demo_slug    = "03-memory"
  name_prefix  = "demos-agentcore-${local.demo_slug}"
  runtime_name = "demos_agentcore_03_memory"
  memory_name  = "demos_agentcore_03_memory"
  ecr_repo     = "demos/agentcore/${local.demo_slug}"
}
