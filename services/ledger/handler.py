"""Ledger service Lambda entry point.

The ledger exposes **no public HTTP routes**. It is invoked synchronously by the
account and transfer services through ``lambda:InvokeFunction``; IAM on the
callers and the function's resource policy restrict who may invoke it.
"""

from __future__ import annotations

from typing import Any

from services.ledger.engine import Ledger
from shared.clients import internal_dispatch
from shared.validation import ACCOUNT_ID_PATTERN, TRANSFER_ID_PATTERN, path_id


def _ledger() -> Ledger:
    return Ledger()


def _open_account(p: dict[str, Any]) -> dict[str, Any]:
    return _ledger().open_account(
        path_id(p.get("account_id"), ACCOUNT_ID_PATTERN, "account_id"),
        customer_id=p["customer_id"],
        currency=p["currency"],
    )


def _get_balance(p: dict[str, Any]) -> dict[str, Any]:
    return _ledger().get_balance(p["account_id"])


def _list_entries(p: dict[str, Any]) -> dict[str, Any]:
    return _ledger().list_entries(p["account_id"], limit=int(p.get("limit", 25)), start_key=p.get("start_key"))


def _set_status(p: dict[str, Any]) -> dict[str, Any]:
    return _ledger().set_status(p["account_id"], p["status"])


def _opening_balance(p: dict[str, Any]) -> dict[str, Any]:
    r = _ledger().post_opening_balance(p["account_id"], p["amount_minor"], p["currency"], p.get("correlation_id"))
    return {"journal_id": r.journal_id, "posted_at": r.posted_at, "replayed": r.replayed}


def _post_transfer(p: dict[str, Any]) -> dict[str, Any]:
    r = _ledger().post_transfer(
        transfer_id=path_id(p.get("transfer_id"), TRANSFER_ID_PATTERN, "transfer_id"),
        source_account_id=p["source_account_id"],
        destination_account_id=p["destination_account_id"],
        amount_minor=p["amount_minor"],
        currency=p["currency"],
        customer_id=p["customer_id"],
        correlation_id=p.get("correlation_id"),
    )
    return {"journal_id": r.journal_id, "posted_at": r.posted_at, "replayed": r.replayed}


def _reverse(p: dict[str, Any]) -> dict[str, Any]:
    r = _ledger().reverse_transfer(p["transfer_id"], reason=p["reason"], operator=p["operator"], correlation_id=p.get("correlation_id"))
    return {"journal_id": r.journal_id, "posted_at": r.posted_at, "replayed": r.replayed}


ACTIONS = {
    "open_account": _open_account,
    "get_balance": _get_balance,
    "list_entries": _list_entries,
    "set_status": _set_status,
    "post_opening_balance": _opening_balance,
    "post_transfer": _post_transfer,
    "reverse_transfer": _reverse,
}


def internal(request: dict[str, Any]) -> dict[str, Any]:
    return internal_dispatch(ACTIONS, request)


def handler(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    return internal(event)
