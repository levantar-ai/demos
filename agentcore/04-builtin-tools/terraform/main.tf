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
  #   terraform/demos/agentcore/04-builtin-tools/terraform.tfstate
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

locals {
  demo_slug        = "04-builtin-tools"
  name_prefix      = "demos-agentcore-${local.demo_slug}"
  runtime_name     = "demos_agentcore_04_builtin_tools"
  interpreter_name = "demos_agentcore_04_interpreter"
  memory_name      = "demos_agentcore_04_memory"
  ecr_repo         = "demos/agentcore/${local.demo_slug}"
}
