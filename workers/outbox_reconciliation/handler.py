"""Outbox reconciliation (scheduled): republish events stuck in PENDING.

Queries the sparse ``PendingIndex`` GSI (only unpublished items carry
``pending_partition``), so no table scan is needed. Items that keep failing
are moved to ``FAILED_PUBLISH`` after ``MAX_ATTEMPTS`` and raise an alarm
metric; they are retained, never deleted (failed-event retention).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from boto3.dynamodb.conditions import Key

from shared import aws, metrics
from shared.config import tables
from shared.ids import parse_iso
from workers.outbox_publisher.handler import mark_published, publish

GRACE = timedelta(minutes=2)
MAX_ATTEMPTS = 10


def run(now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    cutoff = (now - GRACE).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    table = aws.table(tables().outbox)
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {
        "IndexName": "PendingIndex",
        "KeyConditionExpression": Key("pending_partition").eq("PENDING") & Key("pending_since").lt(cutoff),
    }
    while True:
        page = table.query(**kwargs)
        items.extend(page.get("Items", []))
        if "LastEvaluatedKey" not in page or len(items) >= 500:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    oldest_age = 0.0
    if items:
        oldest_age = max((now - parse_iso(i["pending_since"])).total_seconds() for i in items)
    metrics.emit("OutboxPendingCount", len(items))
    metrics.emit("OutboxOldestPendingAgeSeconds", oldest_age, unit="Seconds")

    full = {i["PK"]: aws.to_native(table.get_item(Key={"PK": i["PK"], "SK": "METADATA"}, ConsistentRead=True).get("Item") or {}) for i in items}
    ok, failed = publish([(pk, it["payload"]) for pk, it in full.items() if it.get("status") == "PENDING"])
    for pk in ok:
        mark_published(pk)
    dead = []
    for pk in failed:
        attempts = int(full[pk].get("publish_attempts", 0)) + 1
        update = "SET publish_attempts = :a"
        values: dict[str, Any] = {":a": attempts}
        if attempts >= MAX_ATTEMPTS:
            update += ", #s = :failed REMOVE pending_partition"
            values[":failed"] = "FAILED_PUBLISH"
            dead.append(pk)
        table.update_item(Key={"PK": pk, "SK": "METADATA"}, UpdateExpression=update, ExpressionAttributeValues=values,
                          **({"ExpressionAttributeNames": {"#s": "status"}} if attempts >= MAX_ATTEMPTS else {}))
    if dead:
        metrics.emit("OutboxEventsFailedPermanently", len(dead))
    return {"checked": len(items), "republished": len(ok), "failed": len(failed), "dead_lettered": len(dead), "oldest_pending_age_seconds": oldest_age}


def handler(_event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    return run()
