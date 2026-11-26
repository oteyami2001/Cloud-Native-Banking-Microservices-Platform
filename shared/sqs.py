"""Helpers for SQS-triggered consumers of EventBridge events."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from shared.logging import get_logger, log, set_correlation_id


def unwrap(record: dict[str, Any]) -> dict[str, Any]:
    """Return the domain event envelope from an SQS record carrying an EventBridge event."""

    body = json.loads(record["body"])
    detail = body.get("detail", body)
    if isinstance(detail, str):
        detail = json.loads(detail)
    return detail


def process_batch(event: dict[str, Any], fn: Callable[[dict[str, Any]], None], service: str) -> dict[str, Any]:
    """Process records individually and report partial batch failures.

    Requires ``ReportBatchItemFailures`` on the event source mapping. Failed
    messages are retried by SQS and moved to the DLQ after ``maxReceiveCount``.
    """

    logger = get_logger(service)
    failures = []
    for record in event.get("Records", []):
        try:
            envelope = unwrap(record)
            set_correlation_id(envelope.get("correlation_id"))
            fn(envelope)
        except Exception:
            logger.exception("message.failed", extra={"fields": {"message_id": record.get("messageId")}})
            failures.append({"itemIdentifier": record["messageId"]})
    log(logger, logging.INFO, "batch.processed", records=len(event.get("Records", [])), failures=len(failures))
    return {"batchItemFailures": failures}
