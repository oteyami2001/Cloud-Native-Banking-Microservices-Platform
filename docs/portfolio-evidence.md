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
| Concurrency demo | 10×$300 from $1,000 → 3 posted, 7 rejected, balance $100.00 | `python scripts/simulate_failure.py concurrent-overdraw` |

Not yet available: GitHub Actions run IDs, live AWS results, measured latency,
measured RTO/RPO, actual costs.
