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
  #   terraform/demos/agentcore/05-identity/terraform.tfstate
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

locals {
  demo_slug        = "05-identity"
  name_prefix      = "demos-agentcore-${local.demo_slug}"
  runtime_name     = "demos_agentcore_05_identity"
  interpreter_name = "demos_agentcore_05_interpreter"
  memory_name      = "demos_agentcore_05_memory"
  ecr_repo         = "demos/agentcore/${local.demo_slug}"

  # One pool issues both kinds of token. Its discovery document is what the
  # runtime, the gateway and the credential provider all validate against.
  discovery_url = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.agents.id}/.well-known/openid-configuration"
}
