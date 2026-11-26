# Portfolio evidence log

Record only results that actually happened, with dates, run IDs and links.
Redact account IDs and other identifiers before publishing.

## 2026-11-26 — Phases 0–6 offline foundation (no AWS resources created)
| Evidence | Value | How to reproduce |
|---|---|---|
| Python tests | 170 passed, 0 failed | `make test` |
| Branch coverage (services/shared/workers) | 91% | `make coverage` |
| Terraform | 4 roots `validate` OK; 10 module test suites, 19 runs passed (mocked providers) | `make tf-validate tf-test` |
| Checkov | 313 passed / 0 failed / 98 documented skips; insecure fixture blocked (21 failures) | `make security` |
| TFLint | 0 issues | `make security` |
| Bandit / Ruff | 0 findings | `make lint security` |
| zizmor / actionlint | 0 low+ findings / 0 findings | see security-model.md |
| Reproducible build | identical SHA-256 across two builds | `make build` twice |
| Local demo | $250 transfer conserved $4,850.00; replay did not double post; reconciliation BALANCED | `make local-api` + `make demo` |
| Frontend | `tsc` clean; 28 vitest tests passed; production build 188 kB JS (61 kB gzip); `npm audit` 0 vulnerabilities after upgrading react-router 7.18.5 / vite 7.3.8 / vitest 5.1.0 | `cd frontend && npm ci && npm run lint && npm test && npm run build` |
| Browser walkthrough (Playwright, Chromium) | register → open checking ($4,850 opening journal) + savings → $250 transfer COMPLETED → $4,000 transfer COMPLETED → combined balance still $4,850.00 → history and 5 notifications shown; reviewer queue reachable | `make local-api`, `npm run dev`, scripted walkthrough |
| Concurrency demo | 10×$300 from $1,000 → 3 posted, 7 rejected, balance $100.00 | `python scripts/simulate_failure.py concurrent-overdraw` |

## 2026-11-26 — Phase 7 bootstrap applied (owner-approved, AWS CloudShell)
| Evidence | Value |
|---|---|
| Pre-flight | Discovery + SCP simulation: region-conditioned SCP, 0 denials in us-east-2 ([aws-discovery.md](aws-discovery.md)) |
| Plan review | First plan rejected in review: PR-reachable plan role could write state and read all S3 objects; fixed (`d63383f`) and re-planned |
| `terraform apply` | `Apply complete! Resources: 25 added, 0 changed, 0 destroyed.` (Terraform 1.13.4, AWS provider 6.70.0) |
| Reused | Existing GitHub OIDC provider (not duplicated) |
| `scripts/verify_bootstrap.sh` | 12/12 PASS — both buckets exist, versioned, encrypted, public access blocked; roles plan/apply/deploy/cleanup exist |
| Bootstrap state | Backed up to `s3://novabank-tfstate-…/novabank/bootstrap/terraform.tfstate` (SSE-KMS) |
| Workload resources | None yet (Phase 8 pending) |

## 2026-11-26 — First GitHub Actions runs (`main` @ e038c6e)
| Workflow | Run | Result |
|---|---|---|
| ci — Python (ruff, 170 tests, coverage ≥85%), Terraform (fmt, 4 roots validate, 10 test suites), Frontend (tsc, vitest, build) | [45889062755](https://github.com/oteyami2001/Cloud-Native-Banking-Microservices-Platform/actions/runs/45889062755) | 3/3 jobs success |
| security-scan — Checkov + insecure-fixture negative test + TFLint, Bandit + pip-audit, gitleaks, zizmor, CodeQL (Python, JS/TS) | [45889062736](https://github.com/oteyami2001/Cloud-Native-Banking-Microservices-Platform/actions/runs/45889062736) | 6/6 jobs success (dependency review skipped: push event) |

## 2026-11-26 — First dev apply (partial) and fix
| Step | Run | Result |
|---|---|---|
| terraform-plan | [45898457409](https://github.com/oteyami2001/Cloud-Native-Banking-Microservices-Platform/actions/runs/45898457409) | `Plan: 182 to add, 0 to change, 0 to destroy` @ 748628d |
| terraform-apply (approved) | [45898915092](https://github.com/oteyami2001/Cloud-Native-Banking-Microservices-Platform/actions/runs/45898915092) | **Partial**: plan integrity verified, most resources created; 10 Lambda functions (and dependants) failed — placeholder zip generated at plan time was absent on the apply runner |
| Fix | — | Committed deterministic `placeholder.zip`; regression test forbids plan-time generated files |
| terraform-plan (resume) | [45901933153](https://github.com/oteyami2001/Cloud-Native-Banking-Microservices-Platform/actions/runs/45901933153) | `61 to add, 2 to change, 0 to destroy`; review found the 2 changes were a permanent CloudFront TLS diff (default certificate cannot enforce TLSv1.2) — config corrected to AWS's effective value and exception documented before applying |

| terraform-plan | [45903178161](https://github.com/oteyami2001/Cloud-Native-Banking-Microservices-Platform/actions/runs/45903178161) | `61 to add, 0 to change, 0 to destroy` @ 7dba980 |
| terraform-apply (approved) | [45903536259](https://github.com/oteyami2001/Cloud-Native-Banking-Microservices-Platform/actions/runs/45903536259) | `Apply complete! Resources: 61 added, 0 changed, 0 destroyed.` — dev infrastructure complete (182 resources) |
| Pre-deploy review | — | Fixed 3 deploy-pipeline defects before first use: missing boto3 on runner, smoke test needing a permission the deploy role lacks, alarm check that would have rolled back on placeholder-era alarms |

| deploy-services #1 | [45904772462](https://github.com/oteyami2001/Cloud-Native-Banking-Microservices-Platform/actions/runs/45904772462) | 10 artifacts verified (SHA-256 + attestations), 10 versions published, aliases moved, then **automatic rollback** of all aliases (T27 mechanism exercised). Cause: alarm-based health check counted errors from the placeholder code still being invoked by schedules. Fix: health check now uses Lambda `Errors` per new `ExecutedVersion` |

Dev endpoints (non-secret): API `https://z1czl3y3jh.execute-api.us-east-2.amazonaws.com`, site `https://d163c3lie2sp9w.cloudfront.net`, Cognito domain `https://novabank-dev-1492.auth.us-east-2.amazoncognito.com`.

Not yet available: service deployment run IDs, live AWS results, measured latency,
measured RTO/RPO, actual costs.
