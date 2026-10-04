resource "aws_ecr_repository" "agent" {
  #ts:skip=AC_AWS_0462 The repository is private and reached only through IAM (the runtime role's pull permissions in iam.tf); a repository policy would add nothing
  #ts:skip=AC_AWS_0461 Encrypted with the demo's KMS key in encryption_configuration below; the rule does not read that block
  name                 = local.ecr_repo
  force_delete         = true
  image_tag_mutability = "IMMUTABLE"

  # Changing the encryption replaces the repository, so the image is pushed
  # again after the apply that introduces this (make demo-image).
  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.demo.arn
  }

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Project = "demos"
    Demo    = local.demo_slug
  }
}

resource "aws_ecr_lifecycle_policy" "agent" {
  repository = aws_ecr_repository.agent.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = { type = "expire" }
      }
    ]
  })
}
