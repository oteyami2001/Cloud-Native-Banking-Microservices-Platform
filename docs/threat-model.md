# Threat model (STRIDE, synthetic banking context)

Assets: ledger integrity, customer account data (synthetic), reviewer
privileges, CI/CD credentials, audit evidence.
Trust boundaries: [`diagrams/trust-boundaries.mmd`](../diagrams/trust-boundaries.mmd).

| # | Threat | STRIDE | Mitigation | Verified by |
|---|---|---|---|---|
| 1 | Forged/expired/alg-none token | S | JWT authorizer; service re-checks iss/client/exp/token_use | T03, live_smoke.py |
| 2 | Customer reads another's account by changing the ID (BOLA) | I | Ownership check, 404, cursor binding | T04 |
| 3 | Customer debits another's account | T | Ownership in transfer service + ledger owner condition | test_customer_cannot_debit… |
| 4 | Mass assignment (`customer_id`, `fraud_decision` in body) | T/E | Unknown fields rejected | T17 |
| 5 | Replay of a transfer request | T | Durable idempotency + posting record | T11 |
| 6 | Race to overdraw | T | Conditional atomic writes | T12 |
| 7 | Float/rounding manipulation | T | Integer minor units, float rejection | T09 |
| 8 | Customer self-approves held transfer | E | Scope + group + SoD | T17, SoD test |
| 9 | Insider reviewer approves own/related transfer | E | SoD checks | SoD test |
| 10 | Tampered held-transfer record before approval | T | Request fingerprint + decision fingerprint | tamper test |
| 11 | Fraud service down → unscreened posting | T | Fail closed | T19 |
| 12 | Lost/duplicated events | R | Outbox, reconciliation, idempotent consumers | T20, T21 |
| 13 | Direct DynamoDB write bypassing ledger | T | IAM (ledger-only writes), boundary, reconciliation R1/R4 | static IAM test, tampering test |
| 14 | Evidence altered | R | Versioning, SHA-256, restricted writers | T23 |
| 15 | Token/PII leakage in logs | I | Redaction, no body/header logging | redaction test |
| 16 | DoS / cost exhaustion | D | Throttling, body limits, pagination caps, reserved concurrency, budget alert | api.tftest |
| 17 | Malicious PR steals AWS creds | E | No OIDC for forks; privileged roles bound to protected environments | supply-chain tests, oidc.tftest |
| 18 | Compromised third-party Action | T | SHA pinning, zizmor, minimal permissions | supply-chain tests |
| 19 | Tampered Lambda artifact | T | Reproducible build, checksum + attestation verification | packaging tests |
| 20 | Wrong AWS account targeted | T | `allowed_account_ids`, STS check in workflows | static TF test |
| 21 | XSS steals tokens | I | In-memory tokens, CSP, React escaping | frontend tests |
| 22 | Pagination cursor forged to read another partition | I | Cursor partition validation | cursor test |

## Residual risks
* Fraud rules are illustrative; a real bank needs ML/consortium data and human operations.
* In-memory SPA tokens are still exposed to successful XSS; BFF + HttpOnly cookies recommended for production.
* Single region; no multi-region DR claimed.
* Hot partitions under extreme single-account load.
* The deploy role can update any `novabank-*` function in the region (scoped by name prefix).
* The **apply/cleanup roles are effectively administrator-equivalent within the project scope**:
  they can create `novabank-*` IAM roles with inline policies, so a malicious workflow change
  running under them could escalate. Mitigations: usable only from the protected `dev`/`cleanup`
  environments with a required human reviewer, branch restriction to `main`, plan-integrity
  verification, and no access to `novabank-github-*` roles. A stricter design would require a
  permissions boundary condition on `iam:CreateRole` and lock the boundary policy (future work).
* The plan role (reachable from same-repository pull requests) can read project state and write
  only lock files; reading S3 objects outside the project state is explicitly denied (fixed after
  reviewing the first bootstrap plan, 2026-11-26).
