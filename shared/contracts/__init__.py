"""Domain event envelope, versioning and JSON-schema contract validation."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from shared.config import deployment_version
from shared.ids import new_id, now_iso

EVENT_SOURCE = "novabank.banking"
ENVELOPE_VERSION = "1.0"

#: Event type -> schema file in contracts/events (repository root).
EVENT_SCHEMAS = {
    "TransferRequested": "transfer-requested.json",
    "TransferPendingReview": "transfer-pending-review.json",
    "TransferCompleted": "transfer-completed.json",
    "TransferRejected": "transfer-rejected.json",
    "FraudAlertRaised": "fraud-alert-raised.json",
}


def build_event(
    event_type: str,
    data: dict[str, Any],
    *,
    correlation_id: str | None,
    producer: str,
    entity_id: str,
    schema_version: str = "1",
) -> dict[str, Any]:
    """Return a versioned event envelope (CloudEvents-inspired)."""

    return {
        "event_id": new_id("EVT"),
        "event_type": event_type,
        "schema_version": schema_version,
        "envelope_version": ENVELOPE_VERSION,
        "source": EVENT_SOURCE,
        "producer": producer,
        "entity_id": entity_id,
        "occurred_at": now_iso(),
        "correlation_id": correlation_id or "none",
        "deployment_version": deployment_version(),
        "data": data,
    }


def outbox_item(event: dict[str, Any]) -> dict[str, Any]:
    """Outbox record written atomically with the business transaction.

    ``pending_since`` is a sparse GSI attribute that is removed once the event
    is published, so the outbox reconciliation job can query unpublished
    events without scanning the table.
    """

    return {
        "PK": f"EVENT#{event['event_id']}",
        "SK": "METADATA",
        "event_type": event["event_type"],
        "status": "PENDING",
        "pending_partition": "PENDING",
        "pending_since": event["occurred_at"],
        "created_at": event["occurred_at"],
        "payload": json.dumps(event, separators=(",", ":"), sort_keys=True),
    }


def _schema_dir() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "contracts" / "events"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("contracts/events directory not found")  # pragma: no cover


@cache
def load_schema(event_type: str) -> dict[str, Any]:
    return json.loads((_schema_dir() / EVENT_SCHEMAS[event_type]).read_text())
