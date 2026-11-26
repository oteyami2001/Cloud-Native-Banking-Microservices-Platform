# Architecture Decision Records

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-serverless-first-compute.md) | Lambda first; ECS/EKS as reference tracks | Accepted |
| [0002](0002-dynamodb-ledger.md) | DynamoDB ledger; Aurora PostgreSQL as documented alternative | Accepted |
| [0003](0003-ledger-ownership.md) | Only the ledger service changes balances | Accepted |
| [0004](0004-atomic-double-entry-postings.md) | One TransactWriteItems per balanced journal | Accepted |
| [0005](0005-transactional-outbox.md) | Outbox + Streams publisher, at-least-once | Accepted |
| [0006](0006-idempotency.md) | Principal-bound durable idempotency + permanent posting records | Accepted |
| [0007](0007-fraud-screening.md) | Deterministic versioned rules, fail closed, reviewed holds | Accepted |
| [0008](0008-cognito-authentication.md) | Cognito code + PKCE, JWT authorizer, in-service re-checks | Accepted |
| [0009](0009-environment-isolation.md) | Separate state per environment, dev only deployed | Accepted |
| [0010](0010-deployment-ownership.md) | Terraform owns config; pipeline owns code and aliases | Accepted |
| [0011](0011-artifact-integrity.md) | Reproducible builds, checksums, attestations | Accepted |
| [0012](0012-cost-management.md) | No persistent compute; $25 alert; optional paid features off | Accepted |
| [0013](0013-synchronous-service-calls.md) | Lambda-to-Lambda invoke for screening/posting | Accepted |
