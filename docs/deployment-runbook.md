# Deployment runbook (dev)

Prerequisites: bootstrap complete, GitHub environments and variables set,
explicit approval for Phase 8.

1. **Plan**: run `terraform-plan` (dispatch). Review the step summary and the
   `tfplan.txt` artifact. Expect ~120 resources on first apply.
2. **Apply**: run `terraform-apply` with the plan run id; approve the `dev`
   environment. The job verifies plan checksum and commit before applying.
3. **Seed**: create GL-1000 (idempotent) with the ledger role or an admin session:
   `LEDGER_TABLE=novabank-dev-ledger IDEMPOTENCY_TABLE=novabank-dev-idempotency python scripts/seed_demo_data.py`.
4. **Build**: `build-services` runs on merge to main (or dispatch). Note its run id.
5. **Deploy services**: run `deploy-services` with the build run id; approve.
   It verifies checksums/attestations, publishes versions, moves `live`,
   smoke-tests, waits, checks alarms, and rolls back automatically on failure.
   Integration tests run afterwards.
6. **Frontend**: set the frontend variables from `terraform output platform`
   and run `deploy-frontend`.
7. **Users**: create test users in Cognito (admin-create only by default) and
   add them to `customers`, `fraud-reviewers` or `auditors`. Use synthetic
   e-mail addresses you control. Enable TOTP for reviewers.
8. **Verify**: dashboard, `reconciliation` workflow = BALANCED, record results
   in `docs/validation-scenarios.md` with run IDs.

## Rollback
* Application: re-run `deploy-services` with an earlier build, or
  `aws lambda update-alias --function-name novabank-dev-<svc> --name live --function-version <n>`.
* Infrastructure: revert the commit and plan/apply; never `terraform apply`
  an unreviewed plan.
