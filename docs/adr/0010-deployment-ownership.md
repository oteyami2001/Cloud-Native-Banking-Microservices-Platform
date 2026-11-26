# ADR-0010: Infrastructure vs. application deployment ownership

* Status: Accepted · Date: 2026-11-26

## Decision
Terraform creates each function from a placeholder package and owns its
configuration (role, memory, env vars, tracing, alias existence). It ignores
`filename/source_code_hash/s3_*` and the alias's `function_version`.
`deploy-services` owns code, published versions and the `live` alias.
API Gateway, schedules, event source mappings and internal callers always
target the `live` alias.

## Consequences
+ A later `terraform apply` can never roll back an application release.
+ Rollback = moving the alias to the previous version (seconds).
− Environment variable changes require Terraform (they are configuration).
