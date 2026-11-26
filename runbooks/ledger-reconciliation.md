# Runbook: Ledger reconciliation discrepancy (SEV1)

## Checks (workers/ledger_reconciliation/reconcile.py)
| Check | Meaning | Likely cause |
|---|---|---|
| R1 | Balance ≠ sum of entries | Write that bypassed the ledger (IAM failure) or restore mismatch |
| R2 | Journal debits ≠ credits | Code defect or tampering |
| R3 | Entries ≠ journal lines | Partial restore, manual edit |
| R4 | Assets ≠ liabilities | Any of the above |
| R5 | Negative balance | Condition bypass |
| R6 | COMPLETED transfer without journal (or vice versa) | Restore mismatch between tables |
| R7 | Transfer stuck before posting | Ambiguous ledger failure — see failed-transfer.md |

## Procedure
1. **Freeze** affected accounts (`Ledger().set_status(id, "FROZEN")`). Do not fix balances by hand.
2. Download the report: `aws s3 cp s3://novabank-dev-evidence-<acct>/<s3_key> -` and verify
   `sha256sum` against the audit table record.
3. Identify the first divergence: query entries for the account (`PK=ACCOUNT#…`,
   `begins_with(SK, "ENTRY#")`) and compare with journal headers.
4. Check CloudTrail for non-ledger principals writing to `novabank-dev-ledger`
   (only the ledger role and Terraform should appear).
5. Correct **only** with a documented compensating journal approved by a second person.
6. Re-run reconciliation until `BALANCED`; unfreeze; record the incident.

R7-only reports are operational, not integrity failures.
