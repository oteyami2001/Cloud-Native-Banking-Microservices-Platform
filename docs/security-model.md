# Security model

Machine-readable catalogue: [`policies/security-controls.yaml`](../policies/security-controls.yaml)
(20 controls, evidence paths validated by tests). Framework mapping:
[compliance-mapping.md](compliance-mapping.md). Threats: [threat-model.md](threat-model.md).

## Identity and access
* Customers: Cognito, code + PKCE, optional TOTP MFA (ON in prod reference), 15-minute access tokens.
* Authorization layers: API Gateway JWT + route scopes → service scope/group re-check →
  server-side customer resolution → object ownership → ledger owner condition on the debited account.
* Separation of duties: reviewers cannot approve/reject transfers they initiated or that involve their accounts.
* Workloads: one IAM role per function; DynamoDB `LeadingKeys` conditions
  (`IDENTITY#*` for identity lookups, `CUSTOMER#*`/`POSTING#*` for idempotency);
  permissions boundary denies IAM, KMS key administration and security-service changes;
  ledger table writes only by the ledger role (static test).
* CI/CD: GitHub OIDC; plan (read-only, PRs), apply/deploy (environment `dev`, approval), cleanup
  (environment `cleanup`, approval + phrase). No long-lived keys.

## Data protection
Encryption at rest everywhere (DynamoDB AWS-owned key, S3 SSE-KMS / SSE-S3 for public static
assets, SQS SSE, SNS ops topic unencrypted by design — see CKV_AWS_26). TLS-only bucket and queue policies; HSTS; API Gateway endpoints are TLS 1.2+. The CloudFront site uses the default `*.cloudfront.net` certificate, which applies CloudFront's default security policy (TLSv1); enforcing TLSv1.2_2021 requires a custom domain with an ACM certificate (production reference, catalogued exception CKV_AWS_174).
No secrets exist in the application (public client, IAM roles); Secrets Manager reserved.
Logs redact sensitive keys; tokens and bodies are never logged.

## Application security
Strict validation (no mass assignment), float rejection, body size limits, cursor tampering
protection, safe error messages, security headers, fail-closed dependencies, idempotency.

## Pipeline security (results from local runs on 2026-11-26)
| Tool | Scope | Result |
|---|---|---|
| Ruff (incl. `S` bandit rules) | Python | 0 findings |
| Bandit | services/shared/workers | 0 findings |
| Checkov 3.2.469 | Terraform | 313 passed, 0 failed, 98 skipped with catalogued reasons ([exceptions](../policies/exceptions/checkov.yaml)) |
| TFLint 0.58 + AWS ruleset 0.40 | Terraform | 0 issues (2 fixed) |
| zizmor 1.11 | Workflows | 0 low/medium/high (1 high fixed: `workflow_run` trigger) |
| actionlint 1.7.7 | Workflows | 0 findings |
| pip-audit, gitleaks, CodeQL, dependency review | CI only | Run in `security-scan.yml` (not yet executed in GitHub) |

Trivy was planned for IaC/dependency scanning, but its release artifacts could not be
retrieved from this environment, so it is not wired into CI; Checkov + TFLint cover IaC and
pip-audit covers Python dependencies.

## Audit evidence
Deterministic JSON per event and per reconciliation run with SHA-256 in a versioned bucket;
index in the audit table; writes restricted to audit/reconciliation roles by bucket policy.
Evidence is **tamper-evident** (checksums + versioning), not tamper-proof: Object Lock is
off because it would block cleanup and incur retention cost (ADR-0012).

## Pre-existing account security services
Discovery is read-only. The project never modifies GuardDuty, Security Hub, Config, existing
CloudTrail trails or SCPs. The permissions boundary explicitly denies those APIs.
