variable "aws_region" {
  description = "Region holding the Terraform state bucket"
  type        = string
  default     = "eu-west-2"
}

variable "state_bucket" {
  description = "Name of the Terraform state bucket (globally unique)"
  type        = string
  default     = "levantar-demos-tfstate"
}
