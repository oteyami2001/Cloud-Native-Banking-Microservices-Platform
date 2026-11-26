# ADR-0006: Durable, principal-bound idempotency

* Status: Accepted · Date: 2026-11-26

## Decision
`POST /v1/transfers` requires `Idempotency-Key` (16–128 chars). The record key
is `CUSTOMER#<id> / REQUEST#<key>` — scoped to the authenticated customer —
and stores the SHA-256 of the normalised payload. Same key + same payload →
original outcome; different payload → `422 IDEMPOTENCY_KEY_REUSED`; concurrent
duplicate → `409 REQUEST_IN_PROGRESS` (or resume if posting is pending).

Records have **no TTL**: they live as long as transaction history. DynamoDB's
10-minute `ClientRequestToken` is not relied upon. Independently, the ledger's
permanent `POSTING#<journal>` record and the journal header condition make the
posting itself idempotent even if the request record were lost.

If a dependency fails *before* the transfer exists, the key is released so the
client can retry; after the transfer exists, the outcome is stored.
