# API design

Specification: [`contracts/openapi.yaml`](../contracts/openapi.yaml) (OpenAPI 3.1,
validated in CI; route parity with handlers and Terraform is tested).

| Method | Path | Scope | Group | Service |
|---|---|---|---|---|
| POST | /v1/customers | write | – | customer |
| GET | /v1/customers/me | read | – | customer |
| PATCH | /v1/customers/me | write | – | customer |
| POST | /v1/accounts | write | – | account |
| GET | /v1/accounts | read | – | account |
| GET | /v1/accounts/{id} | read | – | account |
| GET | /v1/accounts/{id}/balance | read | – | account → ledger |
| GET | /v1/accounts/{id}/transactions | read | – | account → ledger |
| POST | /v1/transfers | write | – | transfer |
| GET | /v1/transfers/{id} | read | – (owner) / reviewer | transfer |
| GET | /v1/notifications | read | – | notification |
| GET | /v1/admin/fraud-alerts | admin | fraud-reviewers | fraud |
| POST | /v1/admin/transfers/{id}/approve | admin | fraud-reviewers | transfer |
| POST | /v1/admin/transfers/{id}/reject | admin | fraud-reviewers | transfer |
| GET | /v1/admin/reconciliation | admin | auditors or fraud-reviewers | audit |
| GET | /v1/admin/audit/transfers/{id} | admin | auditors or fraud-reviewers | audit |

`/v1/notifications` and `/v1/admin/audit/transfers/{id}` extend the proposal to
support the notification centre and authorised audit access.

## Conventions
* Identity only from the verified token; customer ids in bodies are rejected (unknown field).
* Objects of other customers → `404` (no enumeration).
* Strict validation: unknown fields rejected, exact types, bounded strings, IDs by pattern, body ≤ 16 KB, floats rejected.
* Pagination: `limit` (1–100) + opaque `cursor` validated to the caller's partition.
* `Idempotency-Key` required on `POST /v1/transfers`.
* Status codes: 201 posted, 202 held, 400 validation, 401 authn, 403 scope/group/SoD, 404, 409 state/in-progress/conflict, 422 business rejection, 503 dependency (fail closed).
* Security headers on every response; `Cache-Control: no-store`; correlation id echoed.
* Rate limits: stage throttling (dev 25 rps, burst 50).
* Logging: route, status, error code and correlation id only — never tokens or bodies.

## Example
```http
POST /v1/transfers
Authorization: Bearer <access token>
Idempotency-Key: 7f9c2ba4e88f827d616045507605853e
Content-Type: application/json

{"source_account_id":"ACC-…","destination_account_id":"ACC-…","amount_minor":25000,"currency":"USD"}
```
```http
HTTP/1.1 201 Created
{"transfer_id":"TRF-…","status":"COMPLETED","amount_minor":25000,"currency":"USD","synthetic":true,…}
```
