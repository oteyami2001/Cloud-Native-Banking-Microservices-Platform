"""Test helpers: API Gateway event builder and a tiny banking test client."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from services.account.handler import handler as account_handler
from services.audit.handler import handler as audit_handler
from services.customer.handler import handler as customer_handler
from services.fraud.handler import handler as fraud_handler
from services.ledger.engine import Ledger
from services.notification.handler import handler as notification_handler
from services.transfer.handler import handler as transfer_handler
from shared import aws
from shared.config import GL_SYNTHETIC_FUNDING_ACCOUNT, tables

ROUTES = {
    "POST /v1/customers": customer_handler,
    "GET /v1/customers/me": customer_handler,
    "PATCH /v1/customers/me": customer_handler,
    "POST /v1/accounts": account_handler,
    "GET /v1/accounts": account_handler,
    "GET /v1/accounts/{id}": account_handler,
    "GET /v1/accounts/{id}/balance": account_handler,
    "GET /v1/accounts/{id}/transactions": account_handler,
    "POST /v1/transfers": transfer_handler,
    "GET /v1/transfers/{id}": transfer_handler,
    "POST /v1/admin/transfers/{id}/approve": transfer_handler,
    "POST /v1/admin/transfers/{id}/reject": transfer_handler,
    "GET /v1/admin/fraud-alerts": fraud_handler,
    "GET /v1/admin/reconciliation": audit_handler,
    "GET /v1/admin/audit/transfers/{id}": audit_handler,
    "GET /v1/notifications": notification_handler,
}

CUSTOMER_SCOPES = "novabank/read novabank/write"
ADMIN_SCOPES = "novabank/read novabank/write novabank/admin"


def claims(sub: str, *, scopes: str = CUSTOMER_SCOPES, groups: str = "[customers]", **extra: Any) -> dict[str, Any]:
    return {
        "sub": sub,
        "username": sub,
        "scope": scopes,
        "cognito:groups": groups,
        "token_use": "access",
        "exp": str(int(time.time()) + 3600),
        **extra,
    }


def api_event(
    route_key: str,
    *,
    claims_: dict[str, Any] | None,
    path: dict[str, str] | None = None,
    body: Any = None,
    headers: dict[str, str] | None = None,
    query: dict[str, str] | None = None,
    raw_body: str | None = None,
) -> dict[str, Any]:
    ctx: dict[str, Any] = {"requestId": f"req-{uuid.uuid4().hex[:16]}"}
    if claims_ is not None:
        ctx["authorizer"] = {"jwt": {"claims": claims_, "scopes": None}}
    return {
        "version": "2.0",
        "routeKey": route_key,
        "headers": headers or {},
        "pathParameters": path,
        "queryStringParameters": query,
        "requestContext": ctx,
        "body": raw_body if raw_body is not None else (json.dumps(body) if body is not None else None),
        "isBase64Encoded": False,
    }


class Bank:
    """Drives the real Lambda handlers in-process against moto."""

    def __init__(self) -> None:
        Ledger().open_account(GL_SYNTHETIC_FUNDING_ACCOUNT, customer_id=None, currency="USD", account_class="ASSET")

    def call(self, route_key: str, who: dict[str, Any] | None, **kw: Any) -> tuple[int, Any]:
        resp = ROUTES[route_key](api_event(route_key, claims_=who, **kw))
        return resp["statusCode"], (json.loads(resp["body"]) if resp["body"] else None)

    def customer(self, name: str = "Synthetic Customer") -> dict[str, Any]:
        sub = str(uuid.uuid4())
        who = claims(sub)
        status, body = self.call("POST /v1/customers", who, body={"display_name": name})
        assert status == 201, body
        return {"claims": who, "customer_id": body["customer_id"], "sub": sub}

    def reviewer(self) -> dict[str, Any]:
        return {"claims": claims(str(uuid.uuid4()), scopes=ADMIN_SCOPES, groups="[fraud-reviewers]")}

    def account(self, owner: dict[str, Any], opening_minor: int | None = None, account_type: str = "CHECKING") -> str:
        body: dict[str, Any] = {"account_type": account_type}
        if opening_minor:
            body["sandbox_opening_balance_minor"] = opening_minor
        status, out = self.call("POST /v1/accounts", owner["claims"], body=body)
        assert status == 201, out
        return out["account_id"]

    def balance(self, account_id: str) -> int:
        return Ledger().get_balance(account_id)["available_balance_minor"]

    def transfer(
        self, owner: dict[str, Any], src: str, dst: str, amount: int, *, key: str | None = None, currency: str = "USD"
    ) -> tuple[int, Any]:
        return self.call(
            "POST /v1/transfers",
            owner["claims"],
            body={"source_account_id": src, "destination_account_id": dst, "amount_minor": amount, "currency": currency},
            headers={"Idempotency-Key": key or uuid.uuid4().hex},
        )

    @staticmethod
    def scan(logical: str) -> list[dict[str, Any]]:
        table = aws.table(getattr(tables(), logical))
        return aws.to_native(table.scan(ConsistentRead=True)["Items"])
