# ADR-0012: Cost management

* Status: Accepted · Date: 2026-11-26

## Decision
No NAT Gateway, ALB, EC2, EKS, Aurora or other persistent compute in the MVP
(enforced by a static test). On-demand DynamoDB, 14-day log retention, low
alarm/metric cardinality, optional reserved concurrency. Paid optional
features default off: WAF, custom domain, customer managed KMS keys, Cognito
advanced security, project CloudTrail, S3 Object Lock (also blocks cleanup).
A $25/month budget **alert** on the Project tag (not a cap). See
docs/cost-model.md.
