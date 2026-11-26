# ADR-0013: Synchronous service calls via Lambda invoke

* Status: Accepted · Date: 2026-11-26

## Context
A transfer must not post without a fraud decision and must report its outcome
to the customer, so screening and posting are synchronous.

## Decision
The transfer service calls account, fraud and ledger through
`lambda:InvokeFunction` on their `live` aliases using a small JSON contract
(`shared/clients.py`). IAM on callers + Lambda resource policies restrict who
may invoke whom. Any transport error maps to `DEPENDENCY_UNAVAILABLE`.
Ambiguous ledger failures leave the transfer in `APPROVED_FOR_POSTING` for
idempotent resumption rather than guessing the outcome.

## Alternatives
Step Functions (clearer orchestration, extra cost/latency per transfer);
private API Gateway routes (more infrastructure). Revisit when moving to containers.
