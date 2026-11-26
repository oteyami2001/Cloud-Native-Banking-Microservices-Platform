"""Durable, principal-bound request idempotency.

Record layout (table ``banking-idempotency``)::

    PK = CUSTOMER#<customer_id>      SK = REQUEST#<idempotency-key>
    status        IN_PROGRESS | COMPLETED
    request_hash  sha256 of the normalised request payload
    resource_id   e.g. the transfer id created for the request
    response      stored response (status code + body) once completed

Rules (see docs/adr/0006-idempotency.md):

* The key is scoped to the authenticated customer, never global.
* Same key + same payload  -> the original outcome is returned.
* Same key + other payload -> ``IDEMPOTENCY_KEY_REUSED`` (HTTP 422).
* Records are retained for the lifetime of the transaction history; no TTL is
  configured, so an old financial request can never be posted again.
* The ledger keeps its own permanent posting record (``POSTING#<journal>``),
  so even a lost or corrupted request record cannot cause a double posting.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from botocore.exceptions import ClientError

from shared import aws
from shared.config import tables
from shared.errors import IdempotencyKeyReusedError, ValidationError
from shared.ids import now_iso
from shared.validation import IDEMPOTENCY_KEY_PATTERN, path_id


def request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def validate_key(key: Any) -> str:
    if key is None:
        raise ValidationError("Idempotency-Key header is required for financial write operations")
    return path_id(key, IDEMPOTENCY_KEY_PATTERN, "Idempotency-Key")


@dataclass(frozen=True)
class IdempotencyRecord:
    is_new: bool
    status: str
    resource_id: str | None
    response: dict[str, Any] | None


class IdempotencyStore:
    def __init__(self, table_name: str | None = None):
        self._table = aws.table(table_name or tables().idempotency)

    @staticmethod
    def _key(customer_id: str, key: str) -> dict[str, str]:
        return {"PK": f"CUSTOMER#{customer_id}", "SK": f"REQUEST#{key}"}

    def begin(self, customer_id: str, key: str, req_hash: str, resource_id: str) -> IdempotencyRecord:
        item = {
            **self._key(customer_id, key),
            "status": "IN_PROGRESS",
            "request_hash": req_hash,
            "resource_id": resource_id,
            "created_at": now_iso(),
        }
        try:
            self._table.put_item(Item=item, ConditionExpression="attribute_not_exists(PK)")
            return IdempotencyRecord(True, "IN_PROGRESS", resource_id, None)
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
        existing = aws.to_native(
            self._table.get_item(Key=self._key(customer_id, key), ConsistentRead=True).get("Item")
        )
        if existing is None:  # pragma: no cover - would require a concurrent delete
            raise IdempotencyKeyReusedError("Idempotency record could not be resolved")
        if existing["request_hash"] != req_hash:
            raise IdempotencyKeyReusedError(
                "Idempotency-Key was already used with a different request payload"
            )
        return IdempotencyRecord(
            False, existing["status"], existing.get("resource_id"), existing.get("response")
        )

    def complete(self, customer_id: str, key: str, req_hash: str, response: dict[str, Any]) -> None:
        self._table.update_item(
            Key=self._key(customer_id, key),
            UpdateExpression="SET #s = :done, #r = :resp, completed_at = :now",
            ConditionExpression="request_hash = :h",
            ExpressionAttributeNames={"#s": "status", "#r": "response"},
            ExpressionAttributeValues={
                ":done": "COMPLETED",
                ":resp": response,
                ":now": now_iso(),
                ":h": req_hash,
            },
        )
