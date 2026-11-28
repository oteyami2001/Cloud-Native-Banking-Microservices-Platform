# Final project report: Phases 7 to 12 (live AWS) · 2026-11-27, teardown 2026-11-28

Continues the [Phase 0–6 report](phase-00-06-report.md). Everything below ran in the
owner's AWS account (us-east-2) through approved Terraform and GitHub Actions runs, or
by the owner in CloudShell and the browser. Data is synthetic throughout.

## 1. Delivered
| Phase | Result |
|---|---|
| 7 Bootstrap | State and artifact buckets and four GitHub OIDC roles (plan, apply, deploy, cleanup), 25 resources, verified 12/12 |
| 8 Dev environment | 182 resources applied from a reviewed, integrity-checked plan |
| 9 Service delivery | 10 Lambda functions built reproducibly (SBOM, attestations), deployed by alias with per-version health checks and automatic rollback |
| 10 Frontend | React SPA on private S3 behind CloudFront (OAC), Cognito sign-in with PKCE, silent session renewal, role-based landing |
| 11 Live validation | 14 of 30 scenarios proven on the running system (list below); all 30 covered by CI or offline tests |
| 12 Portfolio | [Case study](../case-study.html) with screenshots, [AWS console evidence](../aws-console-evidence.md), evidence log, updated cost model |
| Teardown (T30) | All 182 dev resources destroyed on 2026-11-28 by the approved `cleanup` workflow; nothing project-owned left |

## 2. Live validation
T01, T02, T03, T05, T06, T07, T08, T11 (browser), T15, T16 (hold and reviewer rejection),
T18 (reviewer approval), T27 (automatic rollback), T29 (point-in-time restore, 2 min 20 s,
BALANCED), T30 (teardown, below). T28 drift detection has a clean baseline only. Details and run IDs:
[validation register](../validation-scenarios.md), [evidence log](../portfolio-evidence.md).

## 3. Teardown (T30)
On 2026-11-28 the `cleanup` workflow ([46098404662](https://github.com/oteyami2001/Cloud-Native-Banking-Microservices-Platform/actions/runs/46098404662)) ran on `main` @ b544cb0, after the
typed confirmation `destroy-novabank-dev` and approval on the protected `cleanup` environment.

* `terraform destroy` → **182 resources destroyed** in 3 min 50 s (CloudFront took 3 min 12 s of that).
* `scripts/verify_cleanup.sh` found no Lambda functions, DynamoDB tables, SQS queues, event buses,
  HTTP APIs, Cognito pools, buckets, log groups or budgets left.
* The AWS console afterwards showed 0 Lambda functions, 0 DynamoDB tables and 0 CloudWatch alarms
  ([screenshots](../aws-console-evidence.md#after-teardown-t30-2026-11-28)).
* Kept by design: the bootstrap state bucket, artifact bucket and GitHub OIDC roles, so
  [`scripts/rebuild_from_cloudshell.sh`](../../scripts/rebuild_from_cloudshell.sh) can redeploy.
* Gap found: the script's IAM-role and tag checks reported "none" when the cleanup role was denied
  `iam:ListRoles` / `tag:GetResources`. The 10 service roles were in the destroyed state, and the
  script now reports such checks as NOT CHECKED.

## 4. Defects found only in live AWS, all fixed
1. GitHub OIDC subject uses immutable owner/repository IDs; trust policies rewritten.
2. Plan role could write state and read every bucket; narrowed before first apply.
3. Alarm topic encrypted with the AWS-managed SNS key could not receive alarms.
4. Placeholder Lambda zip generated at plan time was missing at apply; now committed.
5. CloudFront default certificate cannot enforce TLS 1.2; configuration matches the effective value, exception documented.
6. Deploy role lacked runner dependencies and smoke-test permissions.
7. Health check counted placeholder-era errors and rolled back a good release; now per new version.
8. Deploy role's site-bucket pattern did not match the bucket name; regression test added.
9. 15-minute token expiry surfaced as a raw 401; silent renewal and expiry redirect added.
10. Reviewers landed on the customer dashboard; role-based landing added.

## 5. Cost
Estimated ≈ $5.50–9.50 per month at demo load, mostly CloudWatch alarms and metrics
([cost model](../cost-model.md)). Not yet confirmed from Cost Explorer. The environment was torn down on 2026-11-28 (T30), which stops these charges.

## 6. Open items
* Confirm actual cost for 26–28 November in Cost Explorer (billing data lags a day or two).
* Need a rebuilt environment: T28 with a deliberate change, latency measurement, a full restore switch-over.
* No compliance certification is claimed; this is a synthetic portfolio sandbox.
