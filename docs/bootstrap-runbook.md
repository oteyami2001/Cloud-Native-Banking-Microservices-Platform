# Bootstrap runbook (one-time, manual, requires approval)

Creates: encrypted/versioned state bucket (native S3 locking), artifact bucket,
GitHub OIDC roles (plan/apply/deploy/cleanup). Reuses an existing GitHub OIDC
provider when one is found.

## 0. Discovery (read-only)
In AWS CloudShell for the **confirmed** target account/region:
```bash
bash scripts/discover_aws.sh us-east-2 | tee discovery.txt
```
Confirm: account id, region, SCPs (deny lists), existing
`token.actions.githubusercontent.com` provider ARN, name collisions with
`novabank-*`, Lambda concurrency quota (≥ 50 unreserved recommended).

## 0b. SCP pre-flight (read-only)
```bash
bash scripts/check_scp_permissions.sh
```
Any `False` in the SCP column means the apply would be blocked; stop and review.

## 1. Apply bootstrap (local state)
```bash
cd terraform/bootstrap
cp terraform.tfvars.example terraform.tfvars   # set expected_account_id, existing_oidc_provider_arn if any
terraform init && terraform plan -out tfplan    # review
terraform apply tfplan
bash ../../scripts/verify_bootstrap.sh us-east-2
```
Keep `terraform.tfstate` for bootstrap safe (it is small; optionally migrate it
into the state bucket under `novabank/bootstrap/`).

## 2. GitHub configuration
Repository → Settings:
* **Environments**: `plan` (no reviewers), `dev` (required reviewer = you,
  prevent self-review if a second reviewer exists), `cleanup` (required reviewer).
  Restrict `dev`/`cleanup` deployment branches to `main`.
* **Variables** (not secrets): `AWS_ACCOUNT_ID`, `AWS_REGION`. After the first
  apply also `API_BASE_URL`, `COGNITO_DOMAIN`, `COGNITO_CLIENT_ID`, `SITE_URL`,
  `FRONTEND_BUCKET`, `FRONTEND_DISTRIBUTION_ID`.
* Branch protection on `main`: required checks `ci`, `security-scan`.

No AWS access keys are stored anywhere.
