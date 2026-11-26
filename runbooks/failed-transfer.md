# Runbook: Failed or stuck transfer

## Transfer states
| State | Money moved? | Action |
|---|---|---|
| `SCREENING` > 5 min | No | Fraud call never returned. Safe to mark `FAILED` (no posting possible: ledger requires `APPROVED_FOR_POSTING`). |
| `PENDING_REVIEW` | No | Normal: awaiting a reviewer. Expires after 72 h (policy). |
| `APPROVED_FOR_POSTING` > 5 min | **Unknown until checked** | Re-drive (below). |
| `COMPLETED` | Yes (atomically) | None. |
| `REJECTED` / `FAILED` | No | Customer may retry with a **new** Idempotency-Key. |

Reconciliation check **R7** reports transfers stuck before posting.

## Re-drive an APPROVED_FOR_POSTING transfer
Posting is idempotent on the transfer id (ledger journal id), so re-driving
can never double-post:

```bash
aws lambda invoke --function-name novabank-dev-transfer:live \
  --cli-binary-format raw-in-base64-out \
  --payload '{"action":"resume_posting","payload":{"transfer_id":"TRF-..."}}' out.json && cat out.json
```

The result is `COMPLETED` (posted now or earlier) or `REJECTED` with a reason
(e.g. `INSUFFICIENT_FUNDS`). A customer retry with the same Idempotency-Key
performs the same resume automatically.

## Verify
* `GET /v1/transfers/{id}` shows the final state.
* Journal header exists exactly once: ledger item `PK=JOURNAL#TRF-...`.
* Reconciliation reports `BALANCED`.

## Authorised reversal (customer dispute, error)
Never delete or edit entries. Post a compensating journal:
`Ledger().reverse_transfer("TRF-...", reason="...", operator="<your id>", correlation_id="INC-...")`.
It requires sufficient funds in the original destination and is itself idempotent (`REV-<id>`).
