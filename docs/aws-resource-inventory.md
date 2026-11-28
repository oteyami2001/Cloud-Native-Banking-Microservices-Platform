# AWS resource inventory (dev, us-east-2)

Everything the project created in account 666102401492, grouped by AWS service, with
where to find it in the console and what is worth a screenshot. Names come from the
Terraform code; the live list can be printed with the commands at the end. The screenshots
taken so far are in [AWS console evidence](aws-console-evidence.md).

Totals: **25 bootstrap resources** (`terraform/bootstrap`) and **182 dev resources**
(`terraform/envs/dev`). Terraform counts every setting as a resource (for example a
bucket, its encryption and its versioning are three), so the console shows fewer items.

Before taking screenshots, select the **Ohio (us-east-2)** region in the console. IAM,
CloudFront and Budgets are global.

## 1. Compute: AWS Lambda (10 functions)
Console: **Lambda → Functions**, search `novabank-dev`.

| Function | Role |
|---|---|
| `novabank-dev-customer` | Customer profiles |
| `novabank-dev-account` | Accounts and history |
| `novabank-dev-ledger` | The only writer of balances |
| `novabank-dev-transfer` | Transfers, idempotency, orchestration |
| `novabank-dev-fraud` | Fraud scoring and review queue |
| `novabank-dev-notification` | Notification consumer (SQS) |
| `novabank-dev-audit` | Audit consumer and evidence (SQS) |
| `novabank-dev-outbox-publisher` | DynamoDB Streams → EventBridge |
| `novabank-dev-outbox-reconciliation` | Republishes pending events every 5 min |
| `novabank-dev-ledger-reconciliation` | Checks the books every hour |

Each function has: an IAM role (`novabank-dev-<name>`), a `live` alias, a CloudWatch log
group (`/aws/lambda/novabank-dev-<name>`), arm64, Python 3.13, X-Ray tracing.

Screenshots: the function list (runtime, architecture); `novabank-dev-ledger` →
**Aliases** tab showing `live` and its version; **Configuration → Permissions** showing its
own role; **Monitor** tab.

## 2. API: Amazon API Gateway
Console: **API Gateway → APIs → `novabank-dev-api`** (HTTP API).

* 16 routes (for example `GET /v1/accounts`, `POST /v1/transfers`, `POST /v1/admin/transfers/{id}/approve`), each with a Lambda integration
* JWT authorizer (Cognito) with route scopes `novabank/read`, `novabank/write`, `novabank/admin`
* `$default` stage with throttling and access logs

Screenshots: **Routes** (all 16), **Authorization** (JWT authorizer attached), **Stages**.

## 3. Identity: Amazon Cognito
Console: **Cognito → User pools → `novabank-dev-users`**.

* User pool (admin-create only, strong password policy)
* App client `novabank-dev-spa` (authorization code + PKCE, no secret)
* Hosted UI domain `novabank-dev-1492`
* Resource server with scopes read / write / admin
* Groups: `customers`, `fraud-reviewers`, `auditors`

Screenshots: **Users** (your two synthetic users, e-mails blurred if public), **Groups**,
**App integration → App client** (OAuth flows and scopes).

## 4. Data: Amazon DynamoDB (9 tables)
Console: **DynamoDB → Tables**, search `novabank-dev`.

| Table | Notes |
|---|---|
| `novabank-dev-customers` | |
| `novabank-dev-accounts` | GSI1 |
| `novabank-dev-ledger` | balances, entries, journals |
| `novabank-dev-transfers` | GSI1 |
| `novabank-dev-idempotency` | durable request keys |
| `novabank-dev-fraud` | GSI1 (review queue) |
| `novabank-dev-outbox` | Streams enabled, sparse `PendingIndex` |
| `novabank-dev-notifications` | GSI1 |
| `novabank-dev-audit` | reconciliation reports |

All on-demand and encrypted. Point-in-time recovery is on for the financial tables; `novabank-dev-notifications` holds derived data and has it off.

Screenshots: the table list; `novabank-dev-ledger` → **Backups** (PITR enabled);
`novabank-dev-outbox` → **Exports and streams** (stream on); **Explore items** on the
ledger showing `ACCOUNT#GL-1000` (synthetic data only).

## 5. Events and messaging
Console: **Amazon EventBridge → Event buses → `novabank-dev-events`**.

* Event bus `novabank-dev-events`, archive `novabank-dev-archive`
* Rules `novabank-dev-notification` and `novabank-dev-audit` (→ SQS)
* Scheduled rules `novabank-dev-outbox-reconciliation` (rate 5 min) and
  `novabank-dev-ledger-reconciliation` (rate 1 hour), on the default bus

Console: **Amazon SQS → Queues**, search `novabank-dev`.

* `novabank-dev-notification` + `novabank-dev-notification-dlq`
* `novabank-dev-audit` + `novabank-dev-audit-dlq`
* `novabank-dev-eventbridge-delivery` + its `-dlq`
* `novabank-dev-outbox-stream-failures`

Plus Lambda event source mappings: outbox stream → publisher, and each queue → its consumer.

Screenshots: the bus with its rules; the scheduled rules; the queue list (DLQs at 0 messages).

## 6. Storage: Amazon S3
Console: **S3 → Buckets**, search `novabank`.

| Bucket | Purpose |
|---|---|
| `novabank-tfstate-666102401492-us-east-2` | Terraform state (bootstrap) |
| `novabank-artifacts-666102401492-us-east-2` | Lambda packages (bootstrap) |
| `novabank-dev-site-666102401492` | Website, private behind CloudFront |
| `novabank-dev-evidence-666102401492` | Reconciliation evidence, versioned, KMS |

Each has public access blocked, encryption, versioning, a lifecycle rule and a bucket policy.

Screenshots: the bucket list; the evidence bucket → **Properties** (versioning, KMS
encryption) and **Objects** under `evidence/reconciliation/`; **Permissions** showing
"Block all public access: On".

## 7. Website: Amazon CloudFront (global)
Console: **CloudFront → Distributions** (`d163c3lie2sp9w.cloudfront.net`, ID `E1K35PZK7Y7H8Z`).

* Distribution with the private S3 origin
* Origin access control `novabank-dev-site`
* Response headers policy `novabank-dev-security-headers`

Screenshots: distribution **General**, **Origins** (OAC), **Behaviors** (redirect to HTTPS).

## 8. Monitoring: Amazon CloudWatch
Console: **CloudWatch**.

* 31 alarms named `novabank-dev-*` (Lambda errors and throttles, DLQs, queue age, API 5xx and
  latency, reconciliation discrepancies, outbox)
* Dashboard `novabank-dev-operations`
* Log groups for each function and the API
* Custom metrics namespace `NovaBank/Banking`
* SNS topic `novabank-dev-ops-alerts` for alarm notifications

Screenshots: **Alarms** (all OK), the dashboard, **Metrics → NovaBank/Banking**, a log
group with JSON logs, **X-Ray → Trace map**.

## 9. Security and governance (IAM is global)
Console: **IAM → Roles**, search `novabank`.

* 10 service roles `novabank-dev-<service>`, each with its own inline policy and the permissions boundary below
* Permissions boundary policy `novabank-dev-service-boundary`
* 4 GitHub roles (bootstrap): `novabank-github-plan`, `-apply`, `-deploy`, `-cleanup`
* GitHub OIDC identity provider `token.actions.githubusercontent.com` (reused, already in the account)

Console: **Billing and Cost Management → Budgets**: `novabank-dev-monthly` ($25).

Screenshots: the role list; `novabank-github-deploy` → **Trust relationships** (OIDC,
repository and environment condition); a service role's policy (least privilege);
**IAM → Identity providers**; the budget.

## 10. Evidence outside AWS (for the same report)
* GitHub → **Actions**: green runs of `terraform-apply`, `deploy-services`, `deploy-frontend`,
  `reconciliation`, `drift-detection`
* GitHub → **Settings → Environments**: `plan`, `dev`, `cleanup` with required reviewers
* The live site: dashboard, fraud review queue, reconciliation page

## Print the live list in CloudShell
Every taggable resource carries `Project = Cloud-Native-Banking-Microservices-Platform`:
```bash
aws resourcegroupstaggingapi get-resources --region us-east-2 --tag-filters Key=Project,Values=Cloud-Native-Banking-Microservices-Platform --query 'ResourceTagMappingList[].ResourceARN' --output text | tr '\t' '\n' | sort
```
CloudFront is registered in us-east-1 for tagging:
```bash
aws resourcegroupstaggingapi get-resources --region us-east-1 --tag-filters Key=Project,Values=Cloud-Native-Banking-Microservices-Platform --query 'ResourceTagMappingList[].ResourceARN' --output text | tr '\t' '\n'
```
The exact Terraform list (all 182 dev resources), from a clone of the repository:
```bash
cd terraform/envs/dev && terraform init -input=false -backend-config="bucket=novabank-tfstate-666102401492-us-east-2" -backend-config="region=us-east-2" >/dev/null && terraform state list
```

Synthetic data only. Blur e-mail addresses and account IDs in screenshots you publish.
