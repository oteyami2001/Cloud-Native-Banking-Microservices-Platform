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

| deploy-services #2 | deploy-services run #2 @ 27aeb6a | **Success**: 10 services deployed (versions 1 → 3), per-version error check clean, offline integration tests passed |
| Live unauthenticated checks (`scripts/live_smoke.py`) | 2026-11-26 | 8/8 requests to 4 protected routes returned 401 (no token and forged `alg: none` token) — **T03 verified live** |

| deploy-frontend #3 (re-run) | after deploy-role fix `3a3b85c` | **Success**: Cognito-mode SPA built (28 tests), synced to the private S3 bucket, CloudFront invalidated; landing page with sandbox banner served at the CloudFront URL (owner screenshot, 2026-11-26) |

| First live banking session (owner, browser) | 2026-11-26 | Cognito sign-in → profile → checking ($4,850 opening journal) + 2 savings → $250 transfer `TRF-01M8D5AANPKV181M1HFC` COMPLETED; checking $4,600 / savings $500; history shows matching −/+ entries; combined $5,350 = sum of opening deposits |

| Fraud hold → reviewer approval (owner, browser) | 2026-11-27 | $6,000 transfer `TRF-01M8D6CKRY7D1MSZ22WN` held PENDING_REVIEW (score 60, FR-001 + FR-007, policy 2026.11.1) with no posting (T16). Reviewer account (`fraud-reviewers`) approved it from the queue → `COMPLETED`; ****1TXA $20,000 → $14,000, ****HZBQ $500 → $6,500, combined $25,350 unchanged (T18). Reconciliation page lists hourly reports, all BALANCED, each with a SHA-256 evidence hash |
| deploy-frontend #5 / #6 | 2026-11-27 @ e767394 | **Success**: session renewal (`7d84659`) and role-based landing (`37cba77`) live; reviewer sign-in lands directly on `/admin/fraud` |
| Duplicate-click check (owner, browser) | 2026-11-27 | Double-click on Confirm produced one transfer `TRF-01M8DPM6BPZTKVMESMWB`, a single −$10.00 history line, ****EJKY $4,590 / ****HZBQ $6,510, combined still $25,350 |
| Insufficient funds (owner, browser) | 2026-11-27 | $300 from Savings ****APZ4 ($250) → `TRF-01M8DQ6A686Y2CFW4WN8` REJECTED `INSUFFICIENT_FUNDS`, "No money moved"; ****APZ4 history still only the opening entry, combined $25,350 |
| Fraud hold → reviewer rejection (owner, browser) | 2026-11-27 | $5,500 from ****1TXA → `TRF-01M8DQDNF21D3C5S2QAH` PENDING_REVIEW (score 60, FR-001 + FR-007); reviewer rejected → `REJECTED`, queue empty; ****1TXA $14,000 / ****HZBQ $6,510 unchanged, no history entry, combined $25,350 |
| reconciliation (on demand) | [45947086172](https://github.com/oteyami2001/Cloud-Native-Banking-Microservices-Platform/actions/runs/45947086172) | **Success**: ledger reconciliation `:live` returned BALANCED. Earlier scheduled run [45901508082](https://github.com/oteyami2001/Cloud-Native-Banking-Microservices-Platform/actions/runs/45901508082) failed with `Function not found …:live` because it fired before the first service deployment created the alias |
| drift-detection ×2 | [45947157411](https://github.com/oteyami2001/Cloud-Native-Banking-Microservices-Platform/actions/runs/45947157411), [45947178232](https://github.com/oteyami2001/Cloud-Native-Banking-Microservices-Platform/actions/runs/45947178232) | **No drift detected**: `terraform plan -detailed-exitcode` returned 0 against live dev (182 resources) |
| Point-in-time restore drill (owner, CloudShell) | 2026-11-27 | Drill 1: `novabank-dev-{ledger,transfers}` restored to 05:10:00Z in **4 min 9 s**, but the verifier could not run (Python 3.11 in CloudShell lacked pip) and the copies were deleted unchecked. Drill 2: restored in **2 min 20 s**; `scripts/verify_restore.py` (read-only) → **BALANCED**, 5 accounts / 6 journals / 2 transfers, assets = liabilities = $25,350.00; ****EJKY $4,600 and ****HZBQ $6,500 (state before the 05:11:10Z $10 transfer, proving the point in time). Temporary tables deleted. Live tables untouched |
| cleanup #1 (T30) | [46098404662](https://github.com/oteyami2001/Cloud-Native-Banking-Microservices-Platform/actions/runs/46098404662) @ b544cb0 | **Success**: `terraform destroy` → 182 resources destroyed in 3 min 50 s (CloudFront took 3 min 12 s); `verify_cleanup.sh` found nothing left. Bootstrap retained |

Dev endpoints (non-secret, **removed 2026-11-28 by T30**; a rebuild gets new ones): API `https://z1czl3y3jh.execute-api.us-east-2.amazonaws.com`, site `https://d163c3lie2sp9w.cloudfront.net`, Cognito domain `https://novabank-dev-1492.auth.us-east-2.amazoncognito.com`.

Not yet available: measured latency, a full restore switch-over, actual costs.
