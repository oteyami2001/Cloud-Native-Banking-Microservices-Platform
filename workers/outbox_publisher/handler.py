"""Transactional outbox publisher (DynamoDB Streams -> EventBridge).

* Only INSERT records of PENDING outbox items are published; the MODIFY
  record produced when an item is marked PUBLISHED is ignored.
* EventBridge ``PutEvents`` can partially fail; every entry's result is
  checked and failed records are reported through ``batchItemFailures``
  (``ReportBatchItemFailures`` on the stream mapping). Lambda then retries
  from the first failed record, bounded by ``maximum_retry_attempts``, after
  which the batch metadata goes to the on-failure SQS destination and the
  outbox reconciliation job republishes from the table.
* Delivery is at-least-once. Consumers are idempotent on ``event_id``.
"""

from __future__ import annotations

import json
from typing import Any

from boto3.dynamodb.types import TypeDeserializer
from botocore.exceptions import ClientError

from shared import aws, metrics
from shared.config import event_bus_name, tables
from shared.contracts import EVENT_SOURCE
from shared.ids import now_iso

_deser = TypeDeserializer()
MAX_ENTRIES = 10  # PutEvents limit per call


def _image(record: dict[str, Any]) -> dict[str, Any]:
    raw = record.get("dynamodb", {}).get("NewImage", {})
    return {k: _deser.deserialize(v) for k, v in raw.items()}


def to_entry(payload: str) -> dict[str, Any]:
    event = json.loads(payload)
    return {
        "Source": EVENT_SOURCE,
        "DetailType": event["event_type"],
        "Detail": payload,
        "EventBusName": event_bus_name(),
    }


def publish(payloads: list[tuple[str, str]]) -> tuple[list[str], list[str]]:
    """Publish (id, payload) pairs. Returns (published ids, failed ids)."""

    events = aws.client("events")
    ok: list[str] = []
    failed: list[str] = []
    for i in range(0, len(payloads), MAX_ENTRIES):
        chunk = payloads[i : i + MAX_ENTRIES]
        try:
            result = events.put_events(Entries=[to_entry(p) for _, p in chunk])
        except ClientError:
            failed.extend(ident for ident, _ in chunk)
            continue
        for (ident, _), entry in zip(chunk, result["Entries"], strict=True):
            (failed if entry.get("ErrorCode") else ok).append(ident)
    if failed:
        metrics.emit("OutboxPublishFailures", len(failed))
    if ok:
        metrics.emit("OutboxEventsPublished", len(ok))
    return ok, failed


def mark_published(pk: str) -> None:
    try:
        aws.table(tables().outbox).update_item(
            Key={"PK": pk, "SK": "METADATA"},
            UpdateExpression="SET #s = :pub, published_at = :now REMOVE pending_partition, pending_since",
            ConditionExpression="#s = :pending",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":pub": "PUBLISHED", ":pending": "PENDING", ":now": now_iso()},
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise


def handler(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    pending: list[tuple[str, str]] = []
    seq: dict[str, str] = {}
    for record in event.get("Records", []):
        if record.get("eventName") != "INSERT":
            continue
        image = _image(record)
        if image.get("status") != "PENDING" or "payload" not in image:
            continue
        pending.append((image["PK"], image["payload"]))
        seq[image["PK"]] = record["dynamodb"]["SequenceNumber"]
    ok, failed = publish(pending)
    for pk in ok:
        mark_published(pk)
    return {"batchItemFailures": [{"itemIdentifier": seq[pk]} for pk in failed]}
