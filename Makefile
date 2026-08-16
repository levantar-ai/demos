# State lives in its own bucket, encrypted with a customer-managed KMS key.
# Demo state carries real secrets (a Cognito app client secret in 02), so
# reading it requires kms:Decrypt as well as s3:GetObject, and decrypts are
# audited in CloudTrail. The bucket denies non-TLS requests and any write
# not encrypted with that key.
AWS_PROFILE ?= lev:andy.rea
TF_STATE_BUCKET ?= levantar-demos-tfstate
TF_STATE_REGION ?= eu-west-2
TF_STATE_KMS_KEY ?= alias/levantar-demos-tfstate
DEMO ?= agentcore/01-first-agent

# Region to authenticate against for the ECR push. Must match the region the
# demo deploys into, which Terraform sets independently via var.aws_region.
AWS_REGION ?= us-east-1

# Deploys reference a git SHA rather than latest. Tags are immutable, so
# building from a dirty tree tags different content with HEAD's SHA and the
# push is refused. Commit first, or set IMAGE_TAG=<tag> explicitly.
IMAGE_TAG ?= $(shell git rev-parse --short HEAD)

.PHONY: demo-init demo-image demo-plan demo-apply demo-destroy fmt fmt-check validate

demo-init:
	cd $(DEMO)/terraform && aws-vault exec $(AWS_PROFILE) -- terraform init \
		-backend-config="bucket=$(TF_STATE_BUCKET)" \
		-backend-config="key=terraform/demos/$(DEMO)/terraform.tfstate" \
		-backend-config="region=$(TF_STATE_REGION)" \
		-backend-config="encrypt=true" \
		-backend-config="kms_key_id=$(TF_STATE_KMS_KEY)"

# The ECR repository has to exist before the image can be pushed, and the image
# has to exist before the runtime that references it. That is why this is a
# targeted apply followed by a build, and why it runs before demo-apply.
demo-image:
	cd $(DEMO)/terraform && aws-vault exec $(AWS_PROFILE) -- terraform apply \
		-auto-approve -var="image_tag=$(IMAGE_TAG)" -target=aws_ecr_repository.agent
	repo=$$(cd $(DEMO)/terraform && aws-vault exec $(AWS_PROFILE) -- \
		terraform output -raw ecr_repository_url) && \
	aws-vault exec $(AWS_PROFILE) -- aws ecr get-login-password --region $(AWS_REGION) \
		| docker login --username AWS --password-stdin "$${repo%%/*}" && \
	docker buildx build --platform linux/arm64 \
		-t "$$repo:$(IMAGE_TAG)" --push $(DEMO)/agent

demo-plan:
	cd $(DEMO)/terraform && aws-vault exec $(AWS_PROFILE) -- terraform plan \
		-var="image_tag=$(IMAGE_TAG)"

demo-apply:
	cd $(DEMO)/terraform && aws-vault exec $(AWS_PROFILE) -- terraform apply \
		-var="image_tag=$(IMAGE_TAG)"

demo-destroy:
	cd $(DEMO)/terraform && aws-vault exec $(AWS_PROFILE) -- terraform destroy \
		-var="image_tag=$(IMAGE_TAG)"

fmt:
	terraform fmt -recursive

fmt-check:
	terraform fmt -check -recursive

validate:
	@for dir in */*/terraform; do \
		[ -d "$$dir" ] || continue; \
		echo "== $$dir"; \
		terraform -chdir=$$dir init -backend=false -input=false >/dev/null && \
		terraform -chdir=$$dir validate || exit 1; \
	done
