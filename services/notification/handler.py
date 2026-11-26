"""Notification service: consumes committed banking events from SQS.

* Generates synthetic in-app notifications (no e-mail/SMS to real people).
* Idempotent: one notification per (event id, channel, recipient), enforced
  with a conditional write, so duplicate deliveries are harmless.
* Operational alerts (FraudAlertRaised) are published to an SNS topic without
  customer identifiers.

Route:
    GET /v1/notifications   the caller's notifications (newest first)
"""

from __future__ import annotations

import json
import os
from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from shared import aws, metrics
from shared.auth import SCOPE_READ
from shared.config import tables
from shared.http import Request, Router, decode_cursor, encode_cursor, page_limit
from shared.identity import customer_id_for
from shared.ids import now_iso
from shared.money import format_minor
from shared.sqs import process_batch

router = Router("notification")


def _messages(event: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Return (customer_id, title, message) tuples for an event."""

    d = event.get("data", {})
    et = event["event_type"]
    amount = f"${format_minor(d['amount_minor'])}" if "amount_minor" in d else ""
    if et == "TransferCompleted":
        out = [
            (
                d["source_customer_id"],
                "Transfer completed",
                f"Your transfer of {amount} to ****{d['destination_account_id'][-4:]} was completed.",
            )
        ]
        if d.get("destination_customer_id") and d["destination_customer_id"] != d["source_customer_id"]:
            out.append(
                (d["destination_customer_id"], "Money received", f"You received {amount} into ****{d['destination_account_id'][-4:]}.")
            )
        elif d.get("destination_customer_id"):
            out[0] = (d["source_customer_id"], "Transfer completed", f"You moved {amount} between your accounts.")
        return out
    if et == "TransferRejected":
        return [
            (
                d["customer_id"],
                "Transfer not completed",
                f"Your transfer of {amount} was not completed ({d.get('reason_code', 'DECLINED')}).",
            )
        ]
    if et == "TransferPendingReview":
        return [
            (
                d["customer_id"],
                "Transfer under review",
                f"Your transfer of {amount} is being reviewed by our security team. No money has moved yet.",
            )
        ]
    if et == "AccountCreated":
        return [(d["customer_id"], "Account opened", f"Your synthetic {d['account_type'].lower()} account is ready.")]
    if et == "CustomerCreated":
        return [(d["customer_id"], "Welcome to NovaBank Digital", "This is a demonstration sandbox. All balances are synthetic.")]
    return []


def handle_event(event: dict[str, Any]) -> None:
    if os.environ.get("NOTIFICATION_FAULT_INJECTION") == "fail" and os.environ.get("ENVIRONMENT", "local") in {"local", "dev"}:
        raise RuntimeError("Injected notification failure")
    table = aws.table(tables().notifications)
    for customer_id, title, message in _messages(event):
        try:
            table.put_item(
                Item={
                    "PK": f"EVENT#{event['event_id']}",
                    "SK": f"CHANNEL#IN_APP#{customer_id}",
                    "GSI1PK": f"CUSTOMER#{customer_id}",
                    "GSI1SK": f"{event['occurred_at']}#{event['event_id']}",
                    "event_type": event["event_type"],
                    "title": title,
                    "message": message,
                    "status": "DELIVERED",
                    "entity_id": event.get("entity_id"),
                    "created_at": now_iso(),
                },
                ConditionExpression="attribute_not_exists(PK)",
            )
            metrics.emit("NotificationDelivered")
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            metrics.emit("DuplicateEventIgnored")
    topic = os.environ.get("OPS_TOPIC_ARN")
    if topic and event["event_type"] == "FraudAlertRaised":
        d = event["data"]
        aws.client("sns").publish(
            TopicArn=topic,
            Subject="NovaBank fraud alert (synthetic)",
            Message=json.dumps(
                {"transfer_id": d["transfer_id"], "decision": d["decision"], "risk_score": d["risk_score"], "rules": d["triggered_rules"]}
            ),
        )


@router.route("GET /v1/notifications")
def list_notifications(req: Request) -> tuple[int, Any]:
    req.principal.require_scope(SCOPE_READ)
    customer_id = customer_id_for(req.principal)
    kwargs: dict[str, Any] = {
        "IndexName": "GSI1",
        "KeyConditionExpression": Key("GSI1PK").eq(f"CUSTOMER#{customer_id}"),
        "ScanIndexForward": False,
        "Limit": page_limit(req.query),
    }
    start = decode_cursor(req.query.get("cursor"), expected={"GSI1PK": f"CUSTOMER#{customer_id}"})
    if start:
        kwargs["ExclusiveStartKey"] = start
    result = aws.table(tables().notifications).query(**kwargs)
    items = [
        {k: v for k, v in aws.to_native(i).items() if k in {"event_type", "title", "message", "status", "entity_id", "created_at"}}
        for i in result.get("Items", [])
    ]
    return 200, {"items": items, "next_cursor": encode_cursor(result.get("LastEvaluatedKey"))}


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    if "routeKey" in event:
        return router(event, context)
    return process_batch(event, handle_event, "notification")
