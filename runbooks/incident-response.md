# Runbook: Incident response

Applies to the `dev` environment of the synthetic NovaBank platform. Pattern
adapted from the AWS AIOps project (detect → classify → contain → recover →
verify → record). Times recorded here must come from real executions.

## 1. Detect
Alarms publish to SNS `novabank-dev-ops-alerts`. Triage order:

| Alarm | Financial impact | First action |
|---|---|---|
| `reconciliation-discrepancies` | **Possible ledger inconsistency** | Go to [ledger-reconciliation.md](ledger-reconciliation.md) immediately |
| `outbox-dead`, `outbox-pending-age`, `stream-failures` | Events delayed; balances correct | [dlq-recovery.md](dlq-recovery.md) §Outbox |
| `dlq-*` | Notifications/audit delayed | [dlq-recovery.md](dlq-recovery.md) |
| `lambda-errors-transfer`, `api-5xx` | Transfers failing (fail closed) | §3 below |
| `lambda-errors-ledger` | Postings failing; no partial posting possible | §3, then [failed-transfer.md](failed-transfer.md) |
| `api-latency-p95`, `lambda-throttles-*` | Degraded | Check throttling/concurrency |

## 2. Classify
* **SEV1** – ledger discrepancy, duplicate posting suspected, unauthorized access.
* **SEV2** – transfers failing or held unexpectedly; DLQ growing.
* **SEV3** – notifications delayed, dashboards missing data.

Record start time (UTC), alarm name, correlation IDs from logs:

```bash
aws logs start-query --log-group-name /aws/lambda/novabank-dev-transfer \
  --start-time $(date -u -d '-30 min' +%s) --end-time $(date -u +%s) \
  --query-string 'fields @timestamp, level, message, correlation_id, code | filter level != "INFO" | sort @timestamp desc | limit 50'
```

## 3. Contain
* Bad release → roll back the alias (fastest, ~seconds):
  ```bash
  aws lambda update-alias --function-name novabank-dev-<service> --name live --function-version <previous>
  ```
  `deploy-services` prints previous/new versions in its step summary.
* Suspected abuse → lower API throttling via Terraform variable, or disable a route.
* Ledger risk → freeze affected accounts (ledger-owned status; blocks both debit and credit):
  ```python
  from services.ledger.engine import Ledger

  Ledger().set_status("ACC-...", "FROZEN")
  ```
  Never edit balances or delete entries. Corrections are compensating journals only.

## 4. Recover and verify
1. Re-drive any `APPROVED_FOR_POSTING` transfers ([failed-transfer.md](failed-transfer.md)).
2. Run reconciliation (`reconciliation` workflow) — must report `BALANCED`.
3. Confirm alarms return to OK.

## 5. Record
Add an entry to `docs/portfolio-evidence.md`: timeline, detection→recovery
duration (measured), root cause, GitHub run IDs, follow-ups.

## Controlled fault injection (dev only)
`fault_injection = { fraud = "unavailable" }` or `{ notification = "fail" }` in
`terraform/envs/dev/terraform.tfvars`, plan/apply, run the scenario, then revert.
The services ignore these flags outside `local`/`dev`.
