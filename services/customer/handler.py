"""Customer service: profiles and identity association.

Routes:
    POST /v1/customers      create the caller's profile (one per identity)
    GET  /v1/customers/me   return the caller's profile
    PATCH /v1/customers/me  update display name / notification preferences

Only synthetic data is accepted. No SSNs, card numbers or real financial data
fields exist in the contract.
"""

from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError

from shared import aws
from shared.auth import SCOPE_READ, SCOPE_WRITE
from shared.config import tables
from shared.contracts import build_event, outbox_item
from shared.errors import ConflictError, NotFoundError
from shared.http import Request, Router
from shared.identity import customer_id_for
from shared.ids import new_id, now_iso
from shared.validation import boolean, string, validate_object

router = Router("customer")

_NAME = string(min_len=1, max_len=80, pattern=r"[\w .,'\-]+")
_PREFS = {"notify_in_app": boolean(), "notify_security_alerts": boolean()}


def _profile(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "customer_id": item["customer_id"],
        "display_name": item["display_name"],
        "status": item["status"],
        "preferences": item.get("preferences", {}),
        "created_at": item["created_at"],
        "synthetic": True,
    }


@router.route("POST /v1/customers")
def create_customer(req: Request) -> tuple[int, Any]:
    req.principal.require_scope(SCOPE_WRITE)
    body = validate_object(req.body or {}, required={"display_name": _NAME}, optional=_PREFS)
    t = tables()
    customer_id = new_id("CUS")
    now = now_iso()
    profile = {
        "PK": f"CUSTOMER#{customer_id}",
        "SK": "PROFILE",
        "customer_id": customer_id,
        "identity_subject": req.principal.subject,
        "display_name": body["display_name"],
        "preferences": {k: body.get(k, True) for k in _PREFS},
        "status": "ACTIVE",
        "created_at": now,
    }
    event = build_event(
        "CustomerCreated",
        {"customer_id": customer_id},
        correlation_id=req.correlation_id,
        producer="customer",
        entity_id=customer_id,
    )
    try:
        aws.dynamodb_client().transact_write_items(
            TransactItems=[
                {
                    "Put": {
                        "TableName": t.customers,
                        "Item": {
                            "PK": f"IDENTITY#{req.principal.subject}",
                            "SK": "CUSTOMER",
                            "customer_id": customer_id,
                            "status": "ACTIVE",
                            "created_at": now,
                        },
                        "ConditionExpression": "attribute_not_exists(PK)",
                    }
                },
                {"Put": {"TableName": t.customers, "Item": profile, "ConditionExpression": "attribute_not_exists(PK)"}},
                {"Put": {"TableName": t.outbox, "Item": outbox_item(event)}},
            ]
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "TransactionCanceledException":
            raise ConflictError("A customer profile already exists for this identity") from exc
        raise
    return 201, _profile(profile)


def _load(req: Request) -> dict[str, Any]:
    customer_id = customer_id_for(req.principal)
    item = aws.table(tables().customers).get_item(Key={"PK": f"CUSTOMER#{customer_id}", "SK": "PROFILE"}, ConsistentRead=True).get("Item")
    if not item:
        raise NotFoundError("Customer profile not found")
    return aws.to_native(item)


@router.route("GET /v1/customers/me")
def get_me(req: Request) -> tuple[int, Any]:
    req.principal.require_scope(SCOPE_READ)
    return 200, _profile(_load(req))


@router.route("PATCH /v1/customers/me")
def update_me(req: Request) -> tuple[int, Any]:
    req.principal.require_scope(SCOPE_WRITE)
    body = validate_object(req.body or {}, required={}, optional={"display_name": _NAME, **_PREFS})
    current = _load(req)
    prefs = {**current.get("preferences", {}), **{k: v for k, v in body.items() if k in _PREFS}}
    result = aws.table(tables().customers).update_item(
        Key={"PK": current["PK"], "SK": "PROFILE"},
        UpdateExpression="SET display_name = :n, preferences = :p, updated_at = :now",
        ExpressionAttributeValues={":n": body.get("display_name", current["display_name"]), ":p": prefs, ":now": now_iso()},
        ReturnValues="ALL_NEW",
    )
    return 200, _profile(aws.to_native(result["Attributes"]))


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    return router(event, context)
