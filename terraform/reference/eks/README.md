# EKS reference (optional future track, not deployed)

* EKS managed node group (or Fargate profiles) in private subnets.
* IRSA / EKS Pod Identity: one Kubernetes service account per banking service
  mapped to its own IAM role (same policies as the Lambda roles).
* Ingress: AWS Load Balancer Controller (internal ALB) behind API Gateway.
* NetworkPolicies so only `transfer` can call `ledger` and `fraud`.
* Argo Rollouts canary with CloudWatch metric analysis for automated rollback.

The EKS control plane is a fixed hourly charge; enable only with explicit
approval for a specific job application.
