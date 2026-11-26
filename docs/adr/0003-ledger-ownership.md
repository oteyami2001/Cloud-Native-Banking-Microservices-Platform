# ADR-0003: The ledger service is the only writer of balances

* Status: Accepted · Date: 2026-11-26

## Decision
Balances (`ACCOUNT#id / BALANCE`) and entries live in the ledger table. Only
the ledger Lambda role has `PutItem/UpdateItem` on it (enforced by IAM and by
`tests/terraform/test_terraform_static.py`). The account service creates
balance records and opening deposits **through** the ledger; the transfer
service requests postings through the ledger. The ledger is not exposed on the
public API; it is invoked only by named callers (Lambda resource policy).

The single cross-service write is the transfer state guard
(`APPROVED_FOR_POSTING → COMPLETED`) committed inside the posting transaction,
which guarantees a transfer is COMPLETED **iff** its journal exists.

## Consequences
+ One place to reason about money; reconciliation can attribute any mismatch.
− Ledger availability gates all postings (fail closed, by design).
