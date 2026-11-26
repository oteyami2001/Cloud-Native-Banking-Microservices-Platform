# ADR-0009: Environment isolation

* Status: Accepted · Date: 2026-11-26

## Decision
`local` (moto / DynamoDB Local, no credentials), `dev` (deployed after
approval), `staging` and `prod` (validated Terraform references, not deployed).
Each environment has its own state key, `allowed_account_ids` guard, name
prefix (`novabank-<env>`) and tfvars. No additional AWS accounts are created;
multi-account separation belongs to the future Landing Zone project.
Bootstrap (state bucket, artifact bucket, OIDC roles) has separate state.
