terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.18"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }

  # Key set at init time:
  #   terraform/demos/agentcore/02-gateway/terraform.tfstate
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

locals {
  demo_slug    = "02-gateway"
  name_prefix  = "demos-agentcore-${local.demo_slug}"
  runtime_name = "demos_agentcore_02_gateway"
  ecr_repo     = "demos/agentcore/${local.demo_slug}"
}
