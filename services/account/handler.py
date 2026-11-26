"""Account service: account metadata, ownership and balance inquiries.

Routes:
    POST /v1/accounts                     open a checking or savings account
    GET  /v1/accounts                     list the caller's accounts
    GET  /v1/accounts/{id}                account details (owner only)
    GET  /v1/accounts/{id}/balance        balance via the ledger (owner only)
    GET  /v1/accounts/{id}/transactions   ledger entries (owner only, paginated)

The account service **never writes balances**. Balance reads and the
synthetic opening deposit are delegated to the ledger service.

Object-level authorization: an account owned by another customer is reported
as ``404 NOT_FOUND`` so account ids cannot be enumerated.
"""

from __future__ import annotations

from typing import Any

from shared import aws, clients
from shared.auth import SCOPE_READ, SCOPE_WRITE
from shared.config import sandbox_opening_balances_enabled, tables
from shared.contracts import build_event, outbox_item
from shared.errors import NotFoundError, ValidationError
from shared.http import Request, Router, decode_cursor, encode_cursor, page_limit
from shared.identity import customer_id_for
from shared.ids import new_id, now_iso
from shared.validation import ACCOUNT_ID_PATTERN, integer, internal_safe_string, path_id, string, validate_object

router = Router("account")
MAX_SANDBOX_OPENING_MINOR = 2_500_000  # USD 25,000.00 synthetic opening deposit


def _public(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "account_id": item["account_id"],
        "account_type": item["account_type"],
        "nickname": item.get("nickname"),
        "currency": item["currency"],
        "status": item["status"],
        "masked_number": item["masked_number"],
        "created_at": item["created_at"],
        "synthetic": True,
    }


def load_account(account_id: str) -> dict[str, Any] | None:
    item = aws.table(tables().accounts).get_item(Key={"PK": f"ACCOUNT#{account_id}", "SK": "METADATA"}, ConsistentRead=True).get("Item")
    return aws.to_native(item) if item else None


def owned_account(req: Request) -> dict[str, Any]:
    account_id = path_id(req.path_params.get("id"), ACCOUNT_ID_PATTERN, "account id")
    customer_id = customer_id_for(req.principal)
    account = load_account(account_id)
    if account is None or account["customer_id"] != customer_id:
        raise NotFoundError("Account not found")
    return account


@router.route("POST /v1/accounts")
def create_account(req: Request) -> tuple[int, Any]:
    req.principal.require_scope(SCOPE_WRITE)
    body = validate_object(
        req.body or {},
        required={"account_type": string(choices={"CHECKING", "SAVINGS"})},
        optional={
            "currency": string(choices={"USD"}),
            "nickname": internal_safe_string(40),
            "sandbox_opening_balance_minor": integer(minimum=1, maximum=MAX_SANDBOX_OPENING_MINOR),
        },
    )
    if "sandbox_opening_balance_minor" in body and not sandbox_opening_balances_enabled():
        raise ValidationError("Sandbox opening balances are disabled in this environment")
    customer_id = customer_id_for(req.principal)
    currency = body.get("currency", "USD")
    account_id = new_id("ACC")
    now = now_iso()

    # 1) Ledger owns the balance record (idempotent on account id).
    clients.ledger().call("open_account", {"account_id": account_id, "customer_id": customer_id, "currency": currency})

    # 2) Account metadata + AccountCreated event, atomically.
    item = {
        "PK": f"ACCOUNT#{account_id}",
        "SK": "METADATA",
        "GSI1PK": f"CUSTOMER#{customer_id}",
        "GSI1SK": f"ACCOUNT#{now}#{account_id}",
        "account_id": account_id,
        "customer_id": customer_id,
        "account_type": body["account_type"],
        "nickname": body.get("nickname"),
        "currency": currency,
        "status": "ACTIVE",
        "masked_number": f"****{account_id[-4:]}",
        "created_at": now,
    }
    event = build_event(
        "AccountCreated",
        {"account_id": account_id, "customer_id": customer_id, "account_type": body["account_type"], "currency": currency},
        correlation_id=req.correlation_id,
        producer="account",
        entity_id=account_id,
    )
    t = tables()
    aws.dynamodb_client().transact_write_items(
        TransactItems=[
            {"Put": {"TableName": t.accounts, "Item": item, "ConditionExpression": "attribute_not_exists(PK)"}},
            {"Put": {"TableName": t.outbox, "Item": outbox_item(event)}},
        ]
    )

    # 3) Documented synthetic opening balance (Dr GL-1000 / Cr deposit).
    opening = body.get("sandbox_opening_balance_minor")
    if opening:
        clients.ledger().call(
            "post_opening_balance",
            {"account_id": account_id, "amount_minor": opening, "currency": currency, "correlation_id": req.correlation_id},
        )
    return 201, _public(item)


@router.route("GET /v1/accounts")
def list_accounts(req: Request) -> tuple[int, Any]:
    req.principal.require_scope(SCOPE_READ)
    customer_id = customer_id_for(req.principal)
    kwargs: dict[str, Any] = {
        "IndexName": "GSI1",
        "KeyConditionExpression": "GSI1PK = :c",
        "ExpressionAttributeValues": {":c": f"CUSTOMER#{customer_id}"},
        "Limit": page_limit(req.query),
    }
    start = decode_cursor(req.query.get("cursor"), expected={"GSI1PK": f"CUSTOMER#{customer_id}"})
    if start:
        kwargs["ExclusiveStartKey"] = start
    result = aws.table(tables().accounts).query(**kwargs)
    # GSI reads are eventually consistent; they are used only for listing,
    # never as the authority for balances or posting eligibility.
    items = [_public(aws.to_native(i)) for i in result.get("Items", [])]
    return 200, {"items": items, "next_cursor": encode_cursor(result.get("LastEvaluatedKey"))}


@router.route("GET /v1/accounts/{id}")
def get_account(req: Request) -> tuple[int, Any]:
    req.principal.require_scope(SCOPE_READ)
    return 200, _public(owned_account(req))


@router.route("GET /v1/accounts/{id}/balance")
def get_balance(req: Request) -> tuple[int, Any]:
    req.principal.require_scope(SCOPE_READ)
    account = owned_account(req)
    balance = clients.ledger().call("get_balance", {"account_id": account["account_id"]})
    return 200, {**balance, "synthetic": True, "as_of": now_iso()}


@router.route("GET /v1/accounts/{id}/transactions")
def get_transactions(req: Request) -> tuple[int, Any]:
    req.principal.require_scope(SCOPE_READ)
    account = owned_account(req)
    pk = f"ACCOUNT#{account['account_id']}"
    start = decode_cursor(req.query.get("cursor"), expected={"PK": pk})
    result = clients.ledger().call(
        "list_entries", {"account_id": account["account_id"], "limit": page_limit(req.query), "start_key": start}
    )
    return 200, {"items": result["entries"], "next_cursor": encode_cursor(result.get("last_key"))}


# ------------------------------------------------------------------ internal
def _get_for_transfer(p: dict[str, Any]) -> dict[str, Any]:
    """Return the minimal account facts the transfer service needs to validate."""

    account = load_account(path_id(p.get("account_id"), ACCOUNT_ID_PATTERN, "account_id"))
    if account is None:
        raise NotFoundError("Account not found")
    return {
        "account_id": account["account_id"],
        "customer_id": account["customer_id"],
        "currency": account["currency"],
        "status": account["status"],
        "created_at": account["created_at"],
    }


def internal(request: dict[str, Any]) -> dict[str, Any]:
    return clients.internal_dispatch({"get_for_transfer": _get_for_transfer}, request)


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    if "routeKey" in event:
        return router(event, context)
    return internal(event)
