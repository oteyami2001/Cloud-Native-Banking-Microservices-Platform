# ADR-0001: Serverless-first compute

* Status: Accepted · Date: 2026-11-26

## Context
Projects 1 and 2 already demonstrated ECS Fargate. NovaBank needs independently
deployable services with near-zero idle cost and strong event integration.

## Decision
Run all seven services and three workers as AWS Lambda (Python 3.13, arm64)
behind an API Gateway HTTP API. No customer VPC: Lambda reaches DynamoDB,
EventBridge, SQS and S3 through public AWS endpoints over TLS with IAM auth.
Handlers are plain Python functions so selected services can be containerised
later (`terraform/reference/ecs-fargate`, `eks`).

## Consequences
+ Idle cost ≈ $0; per-service scaling, roles and releases.
+ No NAT Gateway, VPC endpoints or load balancers.
− Cold starts (mitigated by small packages, no heavy dependencies).
− Synchronous fan-out between functions adds latency (ADR-0013).
− No Kubernetes experience demonstrated in the MVP (optional EKS track).
