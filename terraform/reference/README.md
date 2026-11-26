# Reference implementations — NOT deployed in the MVP

These directories document how NovaBank Digital would evolve beyond the
serverless MVP. Nothing here is referenced by `envs/*`, and nothing here may be
applied without explicit approval and an updated cost model (ADR-0001, ADR-0002).

| Directory | Purpose | Why not in the MVP |
|---|---|---|
| `ecs-fargate/` | Run selected services (e.g. ledger) as containers behind an internal ALB | ALB + NAT/VPC endpoints add ~$40–$80/month idle cost |
| `eks/` | Kubernetes track for job applications that require it | EKS control plane alone is ~$73/month |
| `aurora-postgresql/` | Relational ledger with SQL constraints and reporting | Aurora has a continuous minimum cost; DynamoDB on-demand is ~$0 idle |

The services are already container-ready: each Lambda handler is a plain Python
function with no Lambda-only dependencies, so the same code can run behind a
thin HTTP adapter (see `ecs-fargate/Dockerfile`).
