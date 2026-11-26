# ADR-0002: DynamoDB as the MVP ledger store

* Status: Accepted · Date: 2026-11-26

## Context
A ledger needs atomic multi-item updates, conditional checks and strongly
consistent reads. Aurora PostgreSQL offers relational constraints and SQL
reporting but has a continuous minimum cost.

## Decision
Use DynamoDB on-demand with `TransactWriteItems` (≤100 items, all-or-nothing,
condition expressions) and strongly consistent `GetItem`/`Query` for every
authoritative read. Document an Aurora PostgreSQL ledger as the alternative
(`terraform/reference/aurora-postgresql/ledger_schema.sql`) with constraints
enforced by the database.

## Consequences
+ ~$0 idle; ACID within a transaction; per-item conditional concurrency control.
− Accounting rules (balanced journals, non-negative balances) are enforced by
  application code and conditions, not declarative constraints → compensated by
  reconciliation (R1–R7) and property-based tests.
− Reporting requires designed access patterns; ad-hoc SQL is not available.
− Transactions cost 2× WCU/RCU; a single hot account is limited by per-item throughput.
DynamoDB is not "better for banking" in general; it is the right MVP trade-off here.
