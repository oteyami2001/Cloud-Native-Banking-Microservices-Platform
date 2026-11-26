# NovaBank Digital — Cloud-Native Banking Microservices Platform

> **Synthetic demonstration sandbox.** No real money, no real customer or
> cardholder data, no payment-network connectivity. All balances are fictional.

A secure, event-driven digital-banking platform on AWS that focuses on
**distributed application architecture and financial transaction integrity**:
seven independently deployable Python 3.13 microservices on Lambda, a
double-entry ledger with atomic DynamoDB transactions, durable idempotency, a
transactional outbox, explainable fraud screening with reviewed holds, audit
evidence, and a DevSecOps pipeline with GitHub OIDC.

Project 4 of a cloud-engineering portfolio (after AIOps, Internal Developer
Platform, and Security & Compliance projects).

## Current status
| Area | Status |
|---|---|
| Phases 0–6 (design, local foundation, ledger, APIs, fraud/events, frontend) | ✅ complete offline |
| Terraform, CI/CD workflows, observability (Phases 7/9/10 code) | ✅ written and tested offline — **not applied** |
| AWS deployment (Phase 8+) | ⏸ awaiting account confirmation and approval |

See the [Phase 0–6 report](docs/phase-reports/phase-00-06-report.md) and the
[validation register](docs/validation-scenarios.md) (23/30 scenarios verified offline).

## Architecture
```mermaid
flowchart LR
  B[React SPA] --> CF[CloudFront + OAC] --> S3[(private S3)]
  B --> COG[Cognito PKCE + MFA]
  B --> API[HTTP API + JWT]
  API --> S[customer · account · transfer · fraud · notification · audit]
  S -- invoke --> L[ledger — only balance writer]
  S & L --> D[(DynamoDB)]
  D -- outbox stream --> P[publisher] --> E{{EventBridge}} --> Q[[SQS + DLQ]] --> S
  S --> EV[(S3 evidence, SHA-256)]
```
More: [architecture](docs/architecture.md) · [transfer sequence](diagrams/transfer-sequence.mmd) ·
[data model](docs/database-design.md) · [ADRs](docs/adr/README.md).

### A $250 transfer, atomically
One `TransactWriteItems`: debit checking (only if balance ≥ 25000, ACTIVE, USD,
owned by caller) · credit savings · two immutable entries · journal header
(posts once) · permanent posting record · transfer `APPROVED_FOR_POSTING → COMPLETED`
· `TransferCompleted` outbox event. All or nothing.

## Quick start (no AWS account needed)
```bash
make install          # venv + pinned dev dependencies
make test             # 170 tests: unit, contract, security, invariants, concurrency, terraform-static
make local-api        # offline API on http://127.0.0.1:8080 (moto-backed)
make demo             # in another shell: $250 transfer + fraud hold/approve/reject
cd frontend && npm ci && npm run dev   # UI on http://localhost:5173 (sandbox mode)
```
Terraform (offline): `make tf-validate tf-test`. Security scans: `make security`.

## Repository layout
| Path | Contents |
|---|---|
| `services/` | customer, account, ledger, transfer, fraud, notification, audit |
| `workers/` | outbox publisher, outbox reconciliation, ledger reconciliation |
| `shared/` | auth, money, idempotency, logging, errors, contracts, HTTP router, clients |
| `contracts/` | OpenAPI 3.1 and event JSON Schemas |
| `policies/` | fraud rules, security controls, compliance mapping, exceptions |
| `terraform/` | bootstrap, 14 modules, dev/staging/prod roots, reference designs (ECS, EKS, Aurora) |
| `.github/workflows/` | ci, security-scan, plan, apply, build, deploy, frontend, integration, reconciliation, drift, cleanup |
| `frontend/` | React + TypeScript + Vite banking UI |
| `tests/` | unit, integration, contracts, concurrency, financial invariants, security, terraform |
| `scripts/` | discovery, build, deploy/rollback, local API, simulations, reconciliation, cleanup checks |
| `runbooks/`, `docs/`, `diagrams/` | operations, design, Mermaid diagrams |

> Naming note: worker directories use underscores (`outbox_publisher`) instead
> of the proposal's hyphens so they are importable Python packages.

## Key documents
[Business & accounting model](docs/banking-business-model.md) ·
[Microservices](docs/microservices-design.md) · [API](docs/api-design.md) ·
[Security model](docs/security-model.md) · [Threat model](docs/threat-model.md) ·
[Compliance mapping](docs/compliance-mapping.md) · [Cost model](docs/cost-model.md) ·
[Bootstrap](docs/bootstrap-runbook.md) · [Deployment](docs/deployment-runbook.md) ·
[DR](docs/disaster-recovery.md) · [Evidence log](docs/portfolio-evidence.md)

## Guardrails
No AWS changes without approval · no force-push or unapproved merges · no real
financial data · integer minor units only · no partial or duplicate postings ·
no invented results · no compliance or certification claims.

## License
MIT — see [LICENSE](LICENSE).
