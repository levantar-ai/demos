AWS_PROFILE ?= lev:andy.rea
TF_STATE_BUCKET ?= opptora-state
TF_STATE_REGION ?= eu-west-2
DEMO ?= agentcore/01-first-agent

.PHONY: demo-init demo-plan demo-apply demo-destroy fmt fmt-check validate

demo-init:
	cd $(DEMO)/terraform && aws-vault exec $(AWS_PROFILE) -- terraform init \
		-backend-config="bucket=$(TF_STATE_BUCKET)" \
		-backend-config="key=terraform/demos/$(DEMO)/terraform.tfstate" \
		-backend-config="region=$(TF_STATE_REGION)"

demo-plan:
	cd $(DEMO)/terraform && aws-vault exec $(AWS_PROFILE) -- terraform plan

demo-apply:
	cd $(DEMO)/terraform && aws-vault exec $(AWS_PROFILE) -- terraform apply

demo-destroy:
	cd $(DEMO)/terraform && aws-vault exec $(AWS_PROFILE) -- terraform destroy

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
