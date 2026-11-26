# ADR-0005: Transactional outbox with DynamoDB Streams

* Status: Accepted · Date: 2026-11-26

## Decision
Domain events are written to the outbox table **inside** the business
transaction. A Streams-triggered publisher sends them to EventBridge, checking
each `PutEvents` entry, reporting partial batch failures, bisecting on error,
retrying ≤5 times and sending exhausted batches to an SQS on-failure
destination. A scheduled reconciliation job republishes anything still
`PENDING` via a sparse GSI and parks repeated failures as `FAILED_PUBLISH`
(retained, alarmed). Consumers are idempotent on `event_id`.

## Consequences
+ No event for an uncommitted transaction; no lost event for a committed one.
− Delivery is **at-least-once**, not exactly-once; duplicates are expected and handled.
− Notification failure never rolls back money (it is downstream of the commit).
