# Cost model (dev, us-east-2)

> **Status: preliminary.** Unit prices below are public on-demand list prices
> as understood at the time of writing; they were **not** re-verified against
> the AWS Price List API from this environment (no AWS access). Free-tier
> eligibility is **not** assumed. Re-check with the AWS Pricing Calculator
> before the Phase 8 deployment decision. A budget is an alert, not a cap.

## Workload assumption (synthetic demo month)
50,000 API requests · 5,000 transfers · ~160,000 Lambda invocations
(incl. internal calls, stream/SQS consumers, schedules) at 200 ms / 256 MB ·
2 GB log ingestion · <1 GB DynamoDB data · 31 alarms · ~25 EMF metric series.

| Component | Unit price (list) | Estimate / month |
|---|---|---|
| Lambda requests | $0.20 per 1M | $0.03 |
| Lambda compute (arm64) | $0.0000133334 per GB-s × 8,000 GB-s | $0.11 |
| API Gateway HTTP API | $1.00 per 1M | $0.05 |
| DynamoDB writes (transactional = 2×) | $0.625 per 1M WRU × ~0.2M | $0.13 |
| DynamoDB reads | $0.125 per 1M RRU × ~0.6M | $0.08 |
| DynamoDB storage + PITR | $0.25 + $0.20 per GB-month | $0.45 |
| DynamoDB Streams reads | $0.02 per 100k (first 2.5M often free) | $0.00–$0.05 |
| EventBridge custom events (+ archive) | $1.00 per 1M; archive $0.10/GB | $0.05 |
| SQS | $0.40 per 1M | $0.05 |
| Cognito (≤ 50 MAU, Lite/Essentials tier) | free tier for low MAU (verify) | $0.00–$1.00 |
| CloudFront + S3 site | low volume | $0.00–$0.50 |
| CloudWatch Logs ingestion + storage | $0.50 per GB + $0.03/GB-mo | $1.05 |
| CloudWatch alarms | $0.10 per standard alarm × 31 | $3.10 |
| CloudWatch custom metrics (EMF) | $0.30 per metric × ~25 | $7.50 |
| CloudWatch dashboard | $3.00 (first 3 may be free) | $0.00–$3.00 |
| X-Ray | $5.00 per 1M traces recorded (100k may be free) | $0.00–$0.80 |
| KMS (AWS managed keys) | key free; $0.03 per 10k requests | $0.05 |
| SNS / Budgets | negligible / first budgets free | $0.00 |
| Bootstrap (state + artifacts S3) | | $0.10 |
| **Total (core MVP)** | | **≈ $13 – $18** |

CloudWatch **metrics and alarms dominate**. Levers if needed: alarm only on
error rates of the 5 critical functions (−$1.50), drop throttle alarms (−$1),
reduce EMF metric series (each `Decision`/`Reason` value is a separate metric).

## Excluded / optional (off by default)
| Item | Approx. list price |
|---|---|
| AWS WAF on CloudFront | $5/web ACL + $1/rule + $0.60 per 1M requests |
| Customer managed KMS keys | $1/key-month each |
| Cognito advanced security | per-MAU add-on |
| Project CloudTrail (single region, management events) | first copy of management events free; S3 storage |
| Route 53 + custom domain | $0.50/hosted zone + domain registration |
| S3 Object Lock | storage held for the retention period; blocks cleanup |

## Reference architectures (not deployed)
| Item | Approx. idle cost / month |
|---|---|
| NAT Gateway (1 AZ) | ~$33 + data |
| Internal ALB | ~$16 + LCU |
| ECS Fargate, 2 services × 0.25 vCPU / 0.5 GB, 24×7 | ~$18 |
| EKS control plane | ~$73 |
| Aurora PostgreSQL Serverless v2 (0.5 ACU minimum) | ~$44 + storage |

## Attribution
The budget filters on the `Project` cost-allocation tag (must be activated in
Billing). Untagged usage (e.g. CloudWatch metrics, some data transfer) and
account-wide services (GuardDuty, Config, Security Hub) may not be attributed.
Actual costs must come from Cost Explorer after deployment; none are claimed yet.
