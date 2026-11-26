# ADR-0004: Atomic, balanced double-entry postings

* Status: Accepted · Date: 2026-11-26

## Decision
Every financial change is a **journal** of ≥2 lines whose debits equal credits,
posted with one `TransactWriteItems` containing:

1. per line: conditional balance update (`ACTIVE`, currency, sufficient funds
   for decreases, ceiling for increases, owner check on the debited customer account);
2. per line: immutable entry (`attribute_not_exists`);
3. journal header (`attribute_not_exists` → a journal id posts once);
4. permanent posting record `POSTING#<journal>` in the idempotency table;
5. optional transfer state guard;
6. outbox event.

`TransactionConflict` cancellations are retried with jittered backoff (≤4);
other cancellations are diagnosed with fresh strongly consistent reads into
precise errors (insufficient funds, inactive, currency, duplicate).
Corrections are compensating journals (`REV-<id>`), never edits.

## Consequences
+ No partial posting is possible (tested by injecting a failing item, T14).
+ Concurrent overspend impossible: conditions are evaluated atomically (T12).
− Normal-side metadata is read before the transaction; it is immutable so this is safe.
