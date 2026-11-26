# Aurora PostgreSQL ledger reference (not deployed)

DynamoDB is the MVP ledger (ADR-0002). For a bank needing relational
constraints, ad-hoc SQL reporting and accounting queries, the ledger could move
to Aurora PostgreSQL. `ledger_schema.sql` shows the equivalent design with the
integrity rules enforced **by the database itself**:

* `CHECK` constraints: positive amounts, valid sides, non-negative balances.
* A deferred constraint trigger that rejects any journal whose debits and
  credits do not balance at commit.
* `UNIQUE (journal_id)` = durable posting idempotency.
* `SERIALIZABLE` isolation or `SELECT … FOR UPDATE` on balance rows ordered by
  account id (avoids deadlocks) for concurrent transfers.
* Append-only entries enforced with a trigger + revoked UPDATE/DELETE grants.

Operational notes from a DBA perspective: PITR via automated backups,
cross-AZ replica for failover, `pg_stat_statements` for query tuning, and
partitioning `ledger_entry` by month once volumes justify it.
