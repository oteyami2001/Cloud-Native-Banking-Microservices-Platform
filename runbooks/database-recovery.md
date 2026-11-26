# Runbook: DynamoDB point-in-time recovery

Proposed targets (to be measured, not yet achieved): **RTO ≤ 60 min**, **RPO ≤ 5 min**
(PITR granularity is per second within the 35-day window).

DynamoDB restores create a **new table**. Recovery therefore includes
re-pointing the services and reconciling, not just restoring data.

## 1. Decide scope
Financial consistency spans `ledger`, `transfers`, `idempotency` and `outbox`
(written in the same transactions). Restore **all four to the same timestamp**,
or reconciliation check R6 will flag mismatches.

## 2. Restore (timestamps in UTC)
```bash
T=2026-11-26T10:15:00Z
for t in ledger transfers idempotency outbox; do
  aws dynamodb restore-table-to-point-in-time \
    --source-table-name novabank-dev-$t --target-table-name novabank-dev-$t-restored \
    --restore-date-time $T
done
aws dynamodb wait table-exists --table-name novabank-dev-ledger-restored
```
Record start/finish times for the RTO measurement.

## 3. Validate the restored copy before switching
Run reconciliation against the restored tables locally with read-only credentials:
```bash
LEDGER_TABLE=novabank-dev-ledger-restored TRANSFERS_TABLE=novabank-dev-transfers-restored \
  EVIDENCE_BUCKET=novabank-dev-evidence-<acct> python scripts/reconcile_ledger.py
```
Must be `BALANCED` (R7 entries acceptable).

## 4. Switch
Options, in order of preference:
1. **Data copy back** into the original table names (keeps Terraform state valid): freeze
   writes (set API throttling to 0 or disable routes), export/import or scan/write the
   restored items, unfreeze.
2. **Re-point** Lambda environment variables to the `-restored` tables via Terraform
   variables (requires adding the restored tables to state — document the drift).

Note: the restored tables do not inherit streams, PITR, tags or autoscaling settings;
re-enable streams on `outbox` before switching or events will stop flowing.

## 5. Verify
* Reconciliation `BALANCED`.
* Outbox reconciliation republishes any `PENDING` events (consumers are idempotent).
* Record measured RTO/RPO in `docs/disaster-recovery.md` and `docs/portfolio-evidence.md` (T29).
