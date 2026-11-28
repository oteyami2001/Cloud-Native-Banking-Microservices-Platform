# Deployment runbook (dev)

> **Status:** dev was deployed with these steps on 2026-11-26 and torn down on
> 2026-11-28 (T30, see [Teardown](#teardown-t30)). The bootstrap layer is still in place,
> so the steps below rebuild dev from scratch.

Prerequisites: bootstrap complete, GitHub environments and variables set,
explicit owner approval for each apply (done for dev on 2026-11-26).

1. **Plan**: run `terraform-plan` (dispatch). Review the step summary and the
   `tfplan.txt` artifact. First dev apply created 182 resources (2026-11-26).
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

## One-command rebuild from AWS CloudShell
`scripts/rebuild_from_cloudshell.sh` runs the same steps without GitHub Actions:
bootstrap, dev apply (plan shown first), GL-1000 seed, Lambda build and deploy with
rollback, frontend build and upload, optional Cognito users, and a smoke test. Every
step that changes AWS asks you to type `yes`. It is safe to re-run. Use the GitHub
pipelines for normal changes; this script is for a full rebuild, for example after T30.

### After a rebuild
* The API, site and Cognito addresses change. Update the GitHub variables `API_BASE_URL`,
  `SITE_URL`, `COGNITO_DOMAIN`, `COGNITO_CLIENT_ID`, `FRONTEND_BUCKET` and
  `FRONTEND_DISTRIBUTION_ID` from `terraform output platform` (the script prints them),
  then re-share the new site URL.
* Cognito users and all demo data are gone; recreate users (step 7) and seed GL-1000 (step 3).
* Set `alert_email` in `terraform/envs/dev` if you want budget e-mails; dev ran without them.

## Teardown (T30)
1. GitHub → **Actions → cleanup → Run workflow**, type `destroy-novabank-dev`.
2. Approve the `cleanup` environment. The job assumes `novabank-github-cleanup`, runs
   `terraform destroy` on `terraform/envs/dev` with `evidence_force_destroy=true` (so the
   versioned evidence bucket can be emptied), then `scripts/verify_cleanup.sh`.
3. Read the step summary. Every line should say `none`. A `NOT CHECKED` line means the
   cleanup role may not list that resource type (`iam:ListRoles`, `tag:GetResources`); check it in
   CloudShell, for example
   `aws iam list-roles --query "Roles[?starts_with(RoleName,'novabank-dev')].RoleName" --output text`.
4. Record the run in `docs/validation-scenarios.md` and `docs/portfolio-evidence.md`.

The bootstrap layer (state bucket, artifact bucket, GitHub OIDC roles) is never destroyed
by this workflow. Expect about 4 minutes, most of it CloudFront disabling and deleting the
distribution.

**Done 2026-11-28:** run [46098404662](https://github.com/oteyami2001/Cloud-Native-Banking-Microservices-Platform/actions/runs/46098404662) on `main` @ b544cb0, 02:30–02:34 UTC: "182 destroyed" in
3 min 50 s, verification clean, console showed 0 functions, 0 tables, 0 alarms
([evidence](aws-console-evidence.md#after-teardown-t30-2026-11-28)).

## Rollback
* Application: re-run `deploy-services` with an earlier build, or
  `aws lambda update-alias --function-name novabank-dev-<svc> --name live --function-version <n>`.
* Infrastructure: revert the commit and plan/apply; never `terraform apply`
  an unreviewed plan.
