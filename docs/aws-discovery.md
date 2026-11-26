# AWS discovery results (Phase 0)

Run by the owner in AWS CloudShell on 2026-11-26 with `scripts/discover_aws.sh us-east-2`
(read-only). Identifiers other than the target account are redacted.

| Item | Finding | Impact on the design |
|---|---|---|
| Target | Account `666102401492`, region `us-east-2`, assumed role `AccountFullAccessRole` | Confirmed; used as `expected_account_id` |
| Organization | Member account of an AWS Organization (all features, SCPs enabled); management account `…8776` | Never bypass SCPs; run `scripts/check_scp_permissions.sh` before applying |
| SCP denials observed | `iam:ListAccountAliases`, `guardduty:*`, `securityhub:*`, `access-analyzer:*` (explicit deny, policy `p-zxge1vui`); `organizations:ListPoliciesForTarget` not permitted | The project does not call these services. The permissions boundary already denies them. Full SCP content is not readable from the member account |
| GitHub OIDC provider | **Exists**: `token.actions.githubusercontent.com` | Reuse via `existing_oidc_provider_arn`; do **not** create a second one |
| Terraform state buckets | `acscg-`, `aiops-`, `idp-tfstate-…` from Projects 1–3 | No collision with `novabank-tfstate-…`; previous states are not touched |
| CloudTrail | `idp-management-events` (single region, log validation on) from Project 2 | Keep `create_project_trail = false` and reuse it. If Project 2's cleanup removes that trail, revisit |
| AWS Config | No configuration recorder in us-east-2 | Nothing to preserve; Config remains out of scope |
| GuardDuty / Security Hub / Access Analyzer | Not visible (denied by SCP) | Not modified |
| Existing workloads | No Lambda functions, HTTP/REST APIs, Cognito pools, DynamoDB tables, SQS queues or CloudFront distributions; default event bus only | Clean slate; no name collisions |
| Project-tagged resources | None | — |
| Budgets | `acscg-monthly` $25, `aiops-account-monthly` $30, `idp-project-monthly` $25 | NovaBank adds `novabank-dev-monthly` $25 (Project tag filter). Old budgets left untouched; the owner may delete them if those projects are fully cleaned up |
| Lambda concurrency | Quota 400, unreserved 400 | Sufficient; `reserved_concurrency = -1` (unreserved) |
| Month-to-date cost | ≈ $0.00 (Nov 1–27) | Previous projects appear cleaned up; NovaBank costs will be easy to attribute |

## SCP pre-flight (`scripts/check_scp_permissions.sh`, 2026-11-26)
| Simulation | Denied by SCP | Allowed |
|---|---|---|
| No request context | 33 (all regional services) | 15 (IAM, CloudFront, Budgets, Logs, KMS) |
| `aws:RequestedRegion = us-east-2` | **0** | 48 |
| Region + `Project` request tag | **0** | 48 |

Conclusion: the organization SCP is **region-conditioned**. us-east-2 is permitted for every
action the platform needs; global services are exempt. Deploying in any other region would be
denied. Risk 1 below is therefore closed for the simulated actions.

## Risks recorded
1. ~~**Unknown SCP scope.**~~ Resolved by the pre-flight above (region-conditioned). Only some denied actions are known. Some may hit Phase 7/8 resources
   (for example Cognito or CloudFront, which earlier projects did not use). Mitigation: simulator
   pre-flight, and bootstrap applied before the workload so any denial is found early and cheaply.
2. **Shared OIDC provider.** It is managed outside this project, probably by an earlier project's state.
   If that project's cleanup destroys it, NovaBank's GitHub roles stop working. Mitigation: recorded here;
   recreate it or take ownership in bootstrap with approval.
3. **Shared account.** Budgets filter on the `Project` tag, which must be activated as a cost allocation tag.
