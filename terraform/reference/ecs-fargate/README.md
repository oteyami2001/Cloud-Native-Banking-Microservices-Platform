# ECS Fargate reference (not deployed)

Target topology for moving the **ledger** and **transfer** services to containers:

* VPC with private subnets in 2 AZs, no public IPs on tasks.
* Interface VPC endpoints for DynamoDB (gateway), ECR, CloudWatch Logs, STS,
  Secrets Manager — avoids a NAT Gateway.
* Internal ALB; API Gateway HTTP API → VPC Link → ALB.
* One task role per service with the same least-privilege statements as
  `terraform/modules/platform/main.tf` `local.services`.
* Blue/green via CodeDeploy, mirroring the Project 2 rollback pattern.

Estimated idle cost (us-east-2, 1 task per service, 0.25 vCPU/0.5 GB): see
`docs/cost-model.md#reference-architectures`.
