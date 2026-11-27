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
Run the **read-only** verifier against the restored tables. Do not point the
scheduled reconciliation job at them: it writes evidence, an audit row and an
outbox event, which would publish into the live platform.
In AWS CloudShell first install Python 3.11 with pip and boto3 (the default Python is too old):
`sudo dnf install -y python3.11 python3.11-pip && python3.11 -m pip install --target /tmp/pydeps boto3`,
then prefix the command with `PYTHONPATH=/tmp/pydeps`. Do not delete the restored tables until the verifier has passed.
```bash
python3.11 scripts/verify_restore.py --ledger-table novabank-dev-ledger-restored \
  --transfers-table novabank-dev-transfers-restored --as-of "$T"
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
