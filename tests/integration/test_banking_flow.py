"""End-to-end flows through the real Lambda handlers (moto-backed)."""

from __future__ import annotations

import uuid

import pytest

from tests.support import claims


@pytest.mark.scenario("T01")
def test_customer_registration_succeeds(bank):
    who = claims(str(uuid.uuid4()))
    status, body = bank.call("POST /v1/customers", who, body={"display_name": "Ada Synthetic"})
    assert status == 201
    assert body["customer_id"].startswith("CUS-") and body["synthetic"] is True
    status, me = bank.call("GET /v1/customers/me", who)
    assert status == 200 and me["customer_id"] == body["customer_id"]


def test_second_registration_for_same_identity_conflicts(bank):
    who = claims(str(uuid.uuid4()))
    assert bank.call("POST /v1/customers", who, body={"display_name": "Ada"})[0] == 201
    assert bank.call("POST /v1/customers", who, body={"display_name": "Ada"})[0] == 409


def test_profile_update_and_preferences(bank):
    c = bank.customer()
    status, body = bank.call("PATCH /v1/customers/me", c["claims"], body={"display_name": "New Name", "notify_in_app": False})
    assert status == 200 and body["display_name"] == "New Name" and body["preferences"]["notify_in_app"] is False


@pytest.mark.scenario("T02")
def test_authenticated_customer_can_use_api(bank):
    c = bank.customer()
    assert bank.call("GET /v1/accounts", c["claims"])[0] == 200


@pytest.mark.scenario("T05")
def test_account_creation_with_documented_opening_balance(bank):
    c = bank.customer()
    acc = bank.account(c, opening_minor=485_000)
    status, body = bank.call("GET /v1/accounts/{id}", c["claims"], path={"id": acc})
    assert status == 200 and body["account_type"] == "CHECKING" and body["status"] == "ACTIVE"
    status, accounts = bank.call("GET /v1/accounts", c["claims"])
    assert [a["account_id"] for a in accounts["items"]] == [acc]
    # The opening balance is a balanced journal: Dr GL-1000 / Cr customer deposit.
    headers = [i for i in bank.scan("ledger") if i["SK"] == "HEADER"]
    assert headers[0]["journal_type"] == "OPENING_BALANCE"
    assert {(ln["account_id"], ln["side"]) for ln in headers[0]["lines"]} == {("GL-1000", "D"), (acc, "C")}


@pytest.mark.scenario("T06")
def test_balance_retrieval(bank):
    c = bank.customer()
    acc = bank.account(c, opening_minor=100_000)
    status, body = bank.call("GET /v1/accounts/{id}/balance", c["claims"], path={"id": acc})
    assert status == 200
    assert body["available_balance_minor"] == 100_000 and body["currency"] == "USD" and body["synthetic"] is True


@pytest.mark.scenario("T07")
def test_valid_internal_transfer_succeeds(bank):
    c = bank.customer()
    checking = bank.account(c, opening_minor=485_000)
    savings = bank.account(c, account_type="SAVINGS")
    status, body = bank.transfer(c, checking, savings, 25_000)
    assert status == 201, body
    assert body["status"] == "COMPLETED"
    assert bank.balance(checking) == 460_000
    assert bank.balance(savings) == 25_000
    status, t = bank.call("GET /v1/transfers/{id}", c["claims"], path={"id": body["transfer_id"]})
    assert status == 200 and t["status"] == "COMPLETED"
    status, hist = bank.call("GET /v1/accounts/{id}/transactions", c["claims"], path={"id": checking})
    assert status == 200
    assert [(e["direction"], e["amount_minor"]) for e in hist["items"]] == [("DEBIT", 25_000), ("CREDIT", 485_000)]


def test_transfer_to_another_customer_completes_and_notifies_both(bank):
    from services.notification.handler import handle_event

    a, b = bank.customer(), bank.customer()
    src = bank.account(a, opening_minor=50_000)
    dst = bank.account(b)
    status, body = bank.transfer(a, src, dst, 10_000)
    assert status == 201 and body["status"] == "COMPLETED"
    import json

    events = [json.loads(i["payload"]) for i in bank.scan("outbox")]
    completed = next(e for e in events if e["event_type"] == "TransferCompleted")
    handle_event(completed)
    assert bank.call("GET /v1/notifications", a["claims"])[1]["items"][0]["title"] == "Transfer completed"
    assert bank.call("GET /v1/notifications", b["claims"])[1]["items"][0]["title"] == "Money received"


def test_transaction_history_pagination(bank):
    c = bank.customer()
    src = bank.account(c, opening_minor=100_000)
    dst = bank.account(c)
    for _ in range(3):
        assert bank.transfer(c, src, dst, 1_000)[0] == 201
    status, page1 = bank.call("GET /v1/accounts/{id}/transactions", c["claims"], path={"id": src}, query={"limit": "2"})
    assert status == 200 and len(page1["items"]) == 2 and page1["next_cursor"]
    status, page2 = bank.call(
        "GET /v1/accounts/{id}/transactions", c["claims"], path={"id": src}, query={"limit": "2", "cursor": page1["next_cursor"]}
    )
    assert status == 200 and len(page2["items"]) == 2
    ids = {e["entry_id"] for e in page1["items"]} | {e["entry_id"] for e in page2["items"]}
    assert len(ids) == 4
