# Architecture

NovaBank Digital is a **synthetic** digital-banking platform: no real money,
no real customer data, no payment-network connectivity.

## Logical architecture
Diagram source: [`diagrams/architecture.mmd`](../diagrams/architecture.mmd).

```mermaid
flowchart LR
  B[Browser SPA] --> CF[CloudFront + OAC] --> S3[(private S3 site)]
  B --> COG[Cognito PKCE]
  B --> API[HTTP API + JWT authorizer]
  API --> SVC[customer · account · transfer · fraud · notification · audit λ]
  SVC -- invoke --> LED[ledger λ]
  SVC & LED --> DDB[(DynamoDB)]
  DDB -- outbox stream --> PUB[outbox-publisher λ] --> EB{{EventBridge}}
  EB --> Q1[[SQS notification + DLQ]] & Q2[[SQS audit + DLQ]]
  Q2 --> EV[(S3 evidence)]
```

## Components
| Layer | Service | Notes |
|---|---|---|
| Edge | CloudFront (OAC, security headers, HTTPS-only; TLS 1.2 minimum needs a custom domain + ACM, not in MVP) | Optional WAF (`web_acl_arn`); WAF cannot attach to an HTTP API directly, so API abuse controls are stage throttling + validation |
| Identity | Cognito | Code + PKCE, MFA, scopes, groups |
| API | API Gateway HTTP API | 16 routes, JWT on every route, throttling 25 rps / burst 50 (dev), access logs without headers |
| Compute | 10 Lambda functions (arm64, Python 3.13) | One role each, permissions boundary, X-Ray active, `live` alias |
| Data | 9 DynamoDB tables (on-demand) | PITR on system-of-record tables; outbox stream |
| Events | EventBridge custom bus + archive | Rules to SQS; delivery DLQ |
| Async | SQS (SSE) with DLQs | `ReportBatchItemFailures` |
| Evidence | S3 versioned, SSE-KMS, TLS-only | Writers restricted by bucket policy |
| Ops | CloudWatch EMF metrics, 31 alarms, dashboard, SNS | Low-cardinality dimensions |
| Cost | AWS Budgets ($25 alert) | Project tag filter |

## Integration constraints identified (Phase 1 review)
| Topic | Finding | Design response |
|---|---|---|
| WAF + HTTP API | AWS WAF associates with REST API stages, CloudFront, ALB, AppSync, Cognito — **not** HTTP APIs | WAF optional on CloudFront only; API protected by JWT, throttling, validation |
| `TransactWriteItems` | ≤100 items, ≤4 MB, one operation per item, 2× capacity cost | Transfers use 8 items; self-transfers rejected (same item twice is invalid anyway) |
| Transaction idempotency token | `ClientRequestToken` only lasts 10 minutes | Durable records (ADR-0006) |
| GSIs | Eventually consistent | Never used for balances/eligibility; listing only |
| Streams + Lambda | At-least-once; retries block the shard | Bounded retries, bisect, on-failure destination, outbox reconciliation |
| EventBridge `PutEvents` | ≤10 entries; partial failure returns per-entry errors | Chunking and per-entry checks |
| HTTP API JWT authorizer + Cognito access tokens | Access tokens carry `client_id` not `aud`; authorizer accepts either | Audience configured as the SPA client id; services re-check `client_id` |
| Cognito groups in HTTP API claims | Arrays arrive as strings (`"[a b]"`) | Parser handles both forms |
| Lambda alias + API integration | Permission must target the qualified alias | `aws_lambda_permission.qualifier = "live"` |
| DynamoDB restore | Creates a new table without streams/PITR | Runbook includes re-enabling and reconciliation |
| Lambda in VPC | Would require NAT/endpoints | Not used (ADR-0001) |

## Production reference (not deployed)
Multi-AZ VPC with private subnets, interface endpoints, internal ALB via VPC
Link for containerised services, Aurora PostgreSQL ledger option, customer
managed KMS keys, WAF, custom domain with ACM, separate accounts per
environment (Landing Zone project). See `terraform/reference/`.
