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
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.0"
    }
  }

  # Key set at init time:
  #   terraform/demos/agentcore/06-model-in-the-loop/terraform.tfstate
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

locals {
  demo_slug        = "06-model-in-the-loop"
  name_prefix      = "demos-agentcore-${local.demo_slug}"
  runtime_name     = "demos_agentcore_06_model_in_the_loop"
  interpreter_name = "demos_agentcore_06_interpreter"
  memory_name      = "demos_agentcore_06_memory"
  ecr_repo         = "demos/agentcore/${local.demo_slug}"

  # The foundation model behind the inference profile: the profile id with
  # its region prefix (us., eu., global.) removed.
  foundation_model      = regex("^(?:[a-z]+\\.)?(.+)$", var.model_id)[0]
  inference_profile_arn = "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/${var.model_id}"

  # The pool's discovery document is what the runtime validates the customer's
  # Cognito token against. The gateway does not use it; it validates the
  # resource token the exchange issuer mints (gateway.tf).
  discovery_url = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.agents.id}/.well-known/openid-configuration"
}
