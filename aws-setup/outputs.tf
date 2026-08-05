output "state_bucket" {
  description = "Terraform state bucket, passed to demo stacks via -backend-config"
  value       = aws_s3_bucket.state.id
}

output "state_kms_key_alias" {
  description = "KMS alias for state encryption, passed as kms_key_id at init"
  value       = aws_kms_alias.state.name
}

output "state_kms_key_arn" {
  description = "ARN of the state encryption key"
  value       = aws_kms_key.state.arn
}
