# aws-setup — Terraform state backend

Creates the S3 bucket and KMS key that every demo stack stores its state in.

State for these demos is not inert. Post 02 provisions a Cognito app client,
and the provider reads its `client_secret` back as a computed attribute, so
it lands in state whether you want it there or not — there is no write-only
or ephemeral variant of that resource. The bucket is therefore treated as a
secret store rather than a scratch file:

- **SSE-KMS with a customer managed key**, so reading state needs
  `kms:Decrypt` as well as `s3:GetObject`, and every decrypt is a CloudTrail
  event. Bucket default encryption alone (SSE-S3) gives you neither.
- **Annual key rotation**, versioning, and all public access blocked.
- **A bucket policy that denies the alternatives**: non-TLS requests, writes
  that are not SSE-KMS, and writes under any other key. Defaults only apply
  when the caller does not ask for something else.

## Bootstrap

This stack manages the bucket its own state lives in, so it is created once
by hand and then imported. Run from the repo root with your profile:

```bash
export AWS_PROFILE=lev:andy.rea
BUCKET=levantar-demos-tfstate
REGION=eu-west-2

# 1. Bucket and key, by hand, because Terraform has nowhere to put state yet
KEY=$(aws-vault exec $AWS_PROFILE -- aws kms create-key --region $REGION \
  --description "Terraform state encryption for levantar demos" \
  --query KeyMetadata.KeyId --output text)
aws-vault exec $AWS_PROFILE -- aws kms create-alias --region $REGION \
  --alias-name alias/$BUCKET --target-key-id "$KEY"
aws-vault exec $AWS_PROFILE -- aws kms enable-key-rotation --region $REGION --key-id "$KEY"
aws-vault exec $AWS_PROFILE -- aws s3api create-bucket --bucket $BUCKET \
  --region $REGION --create-bucket-configuration LocationConstraint=$REGION

# 2. Point this stack at it
aws-vault exec $AWS_PROFILE -- terraform -chdir=aws-setup init \
  -backend-config="bucket=$BUCKET" \
  -backend-config="key=aws-setup/terraform.tfstate" \
  -backend-config="region=$REGION" \
  -backend-config="encrypt=true" \
  -backend-config="kms_key_id=$KEY"

# 3. Adopt the three you just made
aws-vault exec $AWS_PROFILE -- terraform -chdir=aws-setup import aws_kms_key.state "$KEY"
aws-vault exec $AWS_PROFILE -- terraform -chdir=aws-setup import aws_kms_alias.state "alias/$BUCKET"
aws-vault exec $AWS_PROFILE -- terraform -chdir=aws-setup import aws_s3_bucket.state "$BUCKET"

# 4. Let Terraform add versioning, encryption, public access block and policy
aws-vault exec $AWS_PROFILE -- terraform -chdir=aws-setup apply
```

Starting from nothing, step 4 creates the remaining four resources. If you
are adopting a bucket that already has them configured, import those too
(`aws_s3_bucket_versioning.state`, `aws_s3_bucket_public_access_block.state`,
`aws_s3_bucket_server_side_encryption_configuration.state` and
`aws_s3_bucket_policy.state`, each with the bucket name as the id) and the
apply becomes a no-op.

A second run of `terraform plan` should report no changes.

## Then the demos

`make demo-init` reads the bucket and key from the `Makefile`, so the demo
stacks pick this up with no further configuration:

```bash
make demo-init DEMO=agentcore/02-gateway
```

## Teardown

The bucket holds the state of everything else, so destroy the demo stacks
first. `force_destroy` is deliberately not set — emptying a versioned bucket
of state files should be a decision, not a side effect.
