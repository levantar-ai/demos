terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.18"
    }
  }

  # This stack manages the bucket its own state lives in, so it is created
  # once by hand and then imported. See README.md for the bootstrap.
  #   Key set at init time: aws-setup/terraform.tfstate
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}
