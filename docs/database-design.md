# Database design (DynamoDB)

All tables: on-demand, `PK`/`SK` strings, encrypted (AWS owned key; CMK
optional). Names are `novabank-<env>-<logical>`; logical names map to the
proposal's `banking-*` tables. Source of truth: `shared/schema.py` (parity
tested against Terraform).

| Logical (proposal) | Owner | Items | GSIs | PITR | Stream |
|---|---|---|---|---|---|
| customers (`banking-customers`) | customer | `CUSTOMER#id/PROFILE`, `IDENTITY#sub/CUSTOMER` | – | ✓ | – |
| accounts (`banking-accounts`) | account | `ACCOUNT#id/METADATA` | GSI1 `CUSTOMER#id` / `ACCOUNT#ts#id` | ✓ | – |
| ledger (`banking-ledger`) | **ledger** | `ACCOUNT#id/BALANCE`, `ACCOUNT#id/ENTRY#ts#journal#n`, `JOURNAL#id/HEADER` | – | ✓ | – |
| transactions (`banking-transactions`) | transfer (ledger: state guard) | `TRANSFER#id/METADATA` | GSI1 `CUSTOMER#id` / `CREATED#ts#id` | ✓ | – |
| idempotency (`banking-idempotency`) | transfer / ledger | `CUSTOMER#id/REQUEST#key`, `POSTING#journal/LEDGER` | – | ✓ | – |
| fraud (`banking-fraud`) | fraud | `CUSTOMER#id/DECISION#ts#id`, `…/RECIPIENT#acc`, `…/FLAGS` | GSI1 sparse `ALERT#OPEN` / `ts#id` | ✓ | – |
| outbox (`banking-outbox`) | all producers | `EVENT#id/METADATA` | PendingIndex sparse `PENDING` / `pending_since` | ✓ | NEW_IMAGE |
| notifications (`banking-notifications`) | notification | `EVENT#id/CHANNEL#IN_APP#customer` | GSI1 `CUSTOMER#id` / `ts#event` | – | – |
| audit (`banking-audit`) | audit | `ENTITY#id/EVENT#ts#id`, `REPORT#RECONCILIATION/RUN#ts#id` | – | ✓ | – |

Changes from the proposal after access-pattern review: ledger entries use a
time-ordered `ENTRY#<posted_at>#<journal>#<line>` sort key (history newest-first
without a GSI); journal headers live in the ledger table; idempotency also
holds permanent posting records; fraud gains `RECIPIENT#`/`FLAGS` items;
notifications include the recipient in the sort key (one event can notify two
customers).

## Access patterns
| # | Pattern | Operation | Consistency |
|---|---|---|---|
| 1 | Resolve caller → customer | GetItem `IDENTITY#sub` | Strong |
| 2 | Account details / ownership | GetItem `ACCOUNT#id/METADATA` | Strong |
| 3 | List my accounts | Query accounts GSI1 | Eventual (display only) |
| 4 | Balance | GetItem `ACCOUNT#id/BALANCE` | **Strong** |
| 5 | History, newest first, paged | Query `ACCOUNT#id`, `begins_with ENTRY#`, desc | Strong |
| 6 | Post transfer | TransactWriteItems (8 items) | Serializable |
| 7 | Transfer status | GetItem `TRANSFER#id` | Strong |
| 8 | Idempotency lookup | Conditional PutItem / GetItem | Strong |
| 9 | Velocity (1 h) | Query `CUSTOMER#id` SK between `DECISION#t-1h` … | Strong, `Select COUNT` |
| 10 | Open fraud alerts | Query fraud GSI1 `ALERT#OPEN` | Eventual (queue view) |
| 11 | Unpublished events | Query outbox PendingIndex | Eventual (job re-reads strongly) |
| 12 | My notifications | Query notifications GSI1 | Eventual |
| 13 | Audit trail of a transfer | Query audit `ENTITY#TRF-…` | Strong |
| 14 | Reconciliation | Paginated Scan of ledger + transactions | Strong; batch job only |

No scans in request paths. GSIs are never used for balances or posting eligibility.

## Transaction boundaries
* **Posting** (ledger): balances + entries + journal header + posting record + transfer state + outbox.
* **Customer registration**: identity pointer + profile + outbox.
* **Account creation**: (ledger balance record, idempotent) then metadata + outbox. An orphan
  zero balance (if metadata write fails) is harmless and reported by reconciliation.
* **Transfer state changes**: conditional update + outbox.
* **Fraud decision**: decision + recipient/alert + outbox.

## Concurrency
Conditional arithmetic on the balance (`available_balance_minor >= :amount`)
inside the transaction serialises competing debits per item; DynamoDB cancels
conflicting transactions (`TransactionConflict`), which the ledger retries with
jitter. `version` increments on every change for auditing/optimistic checks.

## Hot keys
`GL-1000` is touched only by opening deposits (low volume). A very active
single account is bounded by per-partition throughput (~1,000 WCU/s, halved
for transactions) — acceptable for the synthetic workload; sharded GL accounts
would be the production fix.

## Backup, recovery and retention
PITR (35 days) on system-of-record tables; restore runbook in
`runbooks/database-recovery.md`. Idempotency records: retained with history
(no TTL). Ledger entries: immutable, never deleted. Notifications: may be
purged (derived data). Evidence in S3: versioned; noncurrent versions expire
after 90 days.
