"""Fraud detection service.

Internal actions (invoked by the transfer service only):
    screen         evaluate a transfer and persist an immutable decision
    get_decision   fetch a decision server-side (used for review revalidation)
    record_review  close an alert with the reviewer's outcome
    set_flag       operator flag for unusual activity (scripts/runbooks)

Admin route:
    GET /v1/admin/fraud-alerts   open alerts (fraud-reviewers, novabank/admin)

The decision is computed and stored here; the ledger and transfer services
never accept a fraud decision supplied by a customer.
"""

from __future__ import annotations

import os
from datetime import timedelta
from typing import Any

from boto3.dynamodb.conditions import Key

from services.fraud.rules import ScreeningContext, assess, load_policy
from shared import aws, metrics
from shared.auth import GROUP_FRAUD_REVIEWERS, SCOPE_ADMIN
from shared.clients import internal_dispatch
from shared.config import tables
from shared.contracts import build_event, outbox_item
from shared.errors import InvalidStateError, NotFoundError, ValidationError
from shared.http import Request, Router, decode_cursor, encode_cursor, page_limit
from shared.ids import new_id, now_iso, parse_iso
from shared.logging import get_correlation_id

router = Router("fraud")


def _table() -> Any:
    return aws.table(tables().fraud)


def _velocity(customer_id: str, now: str) -> int:
    since = (parse_iso(now) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    result = _table().query(
        KeyConditionExpression=Key("PK").eq(f"CUSTOMER#{customer_id}") & Key("SK").between(f"DECISION#{since}", "DECISION#~"),
        Select="COUNT",
        ConsistentRead=True,
    )
    return int(result["Count"])


def _is_new_recipient(customer_id: str, destination_customer_id: str | None, destination_account_id: str) -> bool:
    if destination_customer_id == customer_id:
        return False  # transfer between the customer's own accounts
    item = _table().get_item(Key={"PK": f"CUSTOMER#{customer_id}", "SK": f"RECIPIENT#{destination_account_id}"}).get("Item")
    return item is None


def _unusual(customer_id: str) -> bool:
    item = _table().get_item(Key={"PK": f"CUSTOMER#{customer_id}", "SK": "FLAGS"}).get("Item")
    return bool(item and item.get("unusual_activity"))


def screen(p: dict[str, Any]) -> dict[str, Any]:
    if os.environ.get("FRAUD_FAULT_INJECTION") == "unavailable" and os.environ.get("ENVIRONMENT", "local") in {"local", "dev"}:
        raise RuntimeError("Injected fraud service failure")
    required = (
        "transfer_id",
        "customer_id",
        "source_account_id",
        "destination_account_id",
        "amount_minor",
        "currency",
        "request_fingerprint",
        "source_account_created_at",
    )
    missing = [k for k in required if k not in p]
    if missing:
        raise ValidationError("Screening request incomplete", details={"fields": missing})

    now = now_iso()
    age_hours = (parse_iso(now) - parse_iso(p["source_account_created_at"])).total_seconds() / 3600
    ctx = ScreeningContext(
        amount_minor=int(p["amount_minor"]),
        velocity_1h=_velocity(p["customer_id"], now),
        new_recipient=_is_new_recipient(p["customer_id"], p.get("destination_customer_id"), p["destination_account_id"]),
        source_account_age_hours=age_hours,
        unusual_activity=_unusual(p["customer_id"]),
    )
    result = assess(ctx)
    decision_id = new_id("FRD")
    sk = f"DECISION#{now}#{decision_id}"
    expires = (parse_iso(now) + timedelta(hours=load_policy()["review_validity_hours"])).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    decision = {
        "PK": f"CUSTOMER#{p['customer_id']}",
        "SK": sk,
        "decision_id": decision_id,
        "transfer_id": p["transfer_id"],
        "customer_id": p["customer_id"],
        "risk_score": result.risk_score,
        "decision": result.decision,
        "triggered_rules": result.triggered_rules,
        "policy_version": result.policy_version,
        "decided_at": now,
        "review_expires_at": expires,
        "correlation_id": get_correlation_id(),
        "request_fingerprint": p["request_fingerprint"],
        "amount_minor": int(p["amount_minor"]),
        "currency": p["currency"],
    }
    if result.decision != "APPROVED":
        decision.update({"alert_status": "OPEN", "GSI1PK": "ALERT#OPEN", "GSI1SK": f"{now}#{decision_id}"})
    t = tables()
    data = {
        k: decision[k] for k in ("decision_id", "transfer_id", "risk_score", "decision", "triggered_rules", "policy_version", "decided_at")
    }
    items: list[dict[str, Any]] = [
        {"Put": {"TableName": t.fraud, "Item": decision, "ConditionExpression": "attribute_not_exists(PK)"}},
        {
            "Put": {
                "TableName": t.outbox,
                "Item": outbox_item(
                    build_event(
                        "FraudScreeningCompleted", data, correlation_id=get_correlation_id(), producer="fraud", entity_id=p["transfer_id"]
                    )
                ),
            }
        },
    ]
    if result.decision != "APPROVED":
        items.append(
            {
                "Put": {
                    "TableName": t.outbox,
                    "Item": outbox_item(
                        build_event(
                            "FraudAlertRaised",
                            {**data, "customer_id": p["customer_id"], "amount_minor": int(p["amount_minor"]), "currency": p["currency"]},
                            correlation_id=get_correlation_id(),
                            producer="fraud",
                            entity_id=p["transfer_id"],
                        )
                    ),
                }
            }
        )
        metrics.emit("FraudAlertRaised", Decision=result.decision)
    else:
        items.append(
            {
                "Put": {
                    "TableName": t.fraud,
                    "Item": {"PK": f"CUSTOMER#{p['customer_id']}", "SK": f"RECIPIENT#{p['destination_account_id']}", "first_seen_at": now},
                }
            }
        )
    aws.dynamodb_client().transact_write_items(TransactItems=items)
    metrics.emit("FraudScreening", Decision=result.decision)
    return {**data, "decision_sk": sk, "review_expires_at": expires, "correlation_id": decision["correlation_id"]}


def get_decision(p: dict[str, Any]) -> dict[str, Any]:
    item = _table().get_item(Key={"PK": f"CUSTOMER#{p['customer_id']}", "SK": p["decision_sk"]}, ConsistentRead=True).get("Item")
    if not item:
        raise NotFoundError("Fraud decision not found")
    item = aws.to_native(item)
    return {k: v for k, v in item.items() if k not in {"PK", "GSI1PK", "GSI1SK"}}


def record_review(p: dict[str, Any]) -> dict[str, Any]:
    outcome = p["outcome"]
    if outcome not in {"APPROVED", "REJECTED"}:
        raise ValidationError("Invalid review outcome")
    now = now_iso()
    try:
        _table().update_item(
            Key={"PK": f"CUSTOMER#{p['customer_id']}", "SK": p["decision_sk"]},
            UpdateExpression="SET alert_status = :closed, review_outcome = :o, reviewed_by = :r, reviewed_at = :now REMOVE GSI1PK, GSI1SK",
            ConditionExpression="alert_status = :open",
            ExpressionAttributeValues={":closed": "CLOSED", ":open": "OPEN", ":o": outcome, ":r": p["reviewer"], ":now": now},
        )
    except aws.dynamodb_client().exceptions.ConditionalCheckFailedException as exc:
        raise InvalidStateError("Fraud alert is not open") from exc
    if outcome == "APPROVED" and p.get("destination_account_id"):
        _table().put_item(
            Item={"PK": f"CUSTOMER#{p['customer_id']}", "SK": f"RECIPIENT#{p['destination_account_id']}", "first_seen_at": now}
        )
    return {"status": "CLOSED", "review_outcome": outcome, "reviewed_at": now}


def set_flag(p: dict[str, Any]) -> dict[str, Any]:
    _table().put_item(
        Item={"PK": f"CUSTOMER#{p['customer_id']}", "SK": "FLAGS", "unusual_activity": bool(p["unusual_activity"]), "updated_at": now_iso()}
    )
    return {"customer_id": p["customer_id"], "unusual_activity": bool(p["unusual_activity"])}


@router.route("GET /v1/admin/fraud-alerts")
def list_alerts(req: Request) -> tuple[int, Any]:
    req.principal.require_scope(SCOPE_ADMIN)
    req.principal.require_group(GROUP_FRAUD_REVIEWERS)
    kwargs: dict[str, Any] = {
        "IndexName": "GSI1",
        "KeyConditionExpression": Key("GSI1PK").eq("ALERT#OPEN"),
        "ScanIndexForward": True,
        "Limit": page_limit(req.query),
    }
    start = decode_cursor(req.query.get("cursor"), expected={"GSI1PK": "ALERT#OPEN"})
    if start:
        kwargs["ExclusiveStartKey"] = start
    result = _table().query(**kwargs)
    fields = (
        "decision_id",
        "transfer_id",
        "risk_score",
        "decision",
        "triggered_rules",
        "policy_version",
        "decided_at",
        "review_expires_at",
        "amount_minor",
        "currency",
    )
    items = [{k: aws.to_native(i).get(k) for k in fields} for i in result.get("Items", [])]
    return 200, {"items": items, "next_cursor": encode_cursor(result.get("LastEvaluatedKey"))}


ACTIONS = {"screen": screen, "get_decision": get_decision, "record_review": record_review, "set_flag": set_flag}


def internal(request: dict[str, Any]) -> dict[str, Any]:
    return internal_dispatch(ACTIONS, request)


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    if "routeKey" in event:
        return router(event, context)
    return internal(event)
