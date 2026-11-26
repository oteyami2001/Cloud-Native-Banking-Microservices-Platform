"""Fraud screening, held transfers and authorised review."""

from __future__ import annotations

import pytest

from shared import clients
from shared.errors import DependencyUnavailableError


@pytest.mark.scenario("T16")
def test_high_risk_transfer_is_held_without_posting(bank):
    c = bank.customer()
    src, dst = bank.account(c, opening_minor=2_000_000), bank.account(bank.customer())
    status, body = bank.transfer(c, src, dst, 600_000)
    assert status == 202 and body["status"] == "PENDING_REVIEW"
    assert "fraud" not in body  # rule details are not disclosed to customers
    assert bank.balance(src) == 2_000_000 and bank.balance(dst) == 0
    reviewer = bank.reviewer()
    status, alerts = bank.call("GET /v1/admin/fraud-alerts", reviewer["claims"])
    assert status == 200
    alert = alerts["items"][0]
    assert alert["transfer_id"] == body["transfer_id"] and alert["decision"] == "PENDING_REVIEW"
    assert "FR-001" in alert["triggered_rules"] and alert["policy_version"]


def test_very_high_risk_transfer_is_rejected(bank):
    c = bank.customer()
    src, dst = bank.account(c, opening_minor=2_000_000), bank.account(bank.customer())
    status, body = bank.transfer(c, src, dst, 950_000)
    assert status == 422 and body["error"]["code"] == "TRANSFER_REJECTED"
    assert body["transfer"]["status"] == "REJECTED" and bank.balance(src) == 2_000_000


def test_velocity_rule_holds_rapid_transfers(bank):
    c = bank.customer()
    src, dst = bank.account(c, opening_minor=1_000_000), bank.account(c)
    statuses = [bank.transfer(c, src, dst, 100)[1]["status"] for _ in range(11)]
    assert statuses[:5] == ["COMPLETED"] * 5
    assert statuses[-1] == "PENDING_REVIEW"


@pytest.mark.scenario("T18")
def test_authorised_approval_is_revalidated_before_posting(bank):
    c = bank.customer()
    src, dst = bank.account(c, opening_minor=2_000_000), bank.account(bank.customer())
    held = bank.transfer(c, src, dst, 600_000)[1]
    reviewer = bank.reviewer()
    status, body = bank.call(
        "POST /v1/admin/transfers/{id}/approve",
        reviewer["claims"],
        path={"id": held["transfer_id"]},
        body={"reason": "Verified with customer"},
    )
    assert status == 200, body
    assert body["status"] == "COMPLETED" and body["reviewed_by"] == reviewer["claims"]["sub"]
    assert bank.balance(src) == 1_400_000 and bank.balance(dst) == 600_000
    # Alert closed; second approval impossible.
    assert bank.call("GET /v1/admin/fraud-alerts", reviewer["claims"])[1]["items"] == []
    assert bank.call("POST /v1/admin/transfers/{id}/approve", reviewer["claims"], path={"id": held["transfer_id"]})[0] == 409


def test_approval_revalidates_balance(bank):
    c = bank.customer()
    src, other = bank.account(c, opening_minor=700_000), bank.account(c)
    dst = bank.account(bank.customer())
    held = bank.transfer(c, src, dst, 600_000)[1]
    assert held["status"] == "PENDING_REVIEW"
    assert bank.transfer(c, src, other, 200_000)[0] == 201  # funds spent meanwhile
    status, body = bank.call("POST /v1/admin/transfers/{id}/approve", bank.reviewer()["claims"], path={"id": held["transfer_id"]})
    assert status == 422 and body["error"]["code"] == "INSUFFICIENT_FUNDS"
    assert bank.balance(src) == 500_000 and bank.balance(dst) == 0


def test_approval_rejects_tampered_transfer_record(bank):
    from shared import aws
    from shared.config import tables

    c = bank.customer()
    src, dst = bank.account(c, opening_minor=2_000_000), bank.account(bank.customer())
    held = bank.transfer(c, src, dst, 600_000)[1]
    aws.table(tables().transfers).update_item(
        Key={"PK": f"TRANSFER#{held['transfer_id']}", "SK": "METADATA"},
        UpdateExpression="SET amount_minor = :a",
        ExpressionAttributeValues={":a": 1_900_000},
    )
    status, body = bank.call("POST /v1/admin/transfers/{id}/approve", bank.reviewer()["claims"], path={"id": held["transfer_id"]})
    assert status == 409 and "integrity" in body["error"]["message"]
    assert bank.balance(src) == 2_000_000


def test_approval_rejects_frozen_account(bank):
    from services.ledger.engine import Ledger

    c = bank.customer()
    src, dst = bank.account(c, opening_minor=2_000_000), bank.account(bank.customer())
    held = bank.transfer(c, src, dst, 600_000)[1]
    Ledger().set_status(dst, "FROZEN")
    status, body = bank.call("POST /v1/admin/transfers/{id}/approve", bank.reviewer()["claims"], path={"id": held["transfer_id"]})
    assert status == 422 and body["error"]["code"] == "ACCOUNT_NOT_ACTIVE"
    assert bank.balance(src) == 2_000_000


def test_reviewer_can_reject_held_transfer(bank):
    c = bank.customer()
    src, dst = bank.account(c, opening_minor=2_000_000), bank.account(bank.customer())
    held = bank.transfer(c, src, dst, 600_000)[1]
    status, body = bank.call(
        "POST /v1/admin/transfers/{id}/reject", bank.reviewer()["claims"], path={"id": held["transfer_id"]}, body={"reason": "Suspicious"}
    )
    assert status == 200 and body["status"] == "REJECTED" and body["reason_code"] == "REVIEW_REJECTED"
    assert bank.call("GET /v1/transfers/{id}", c["claims"], path={"id": held["transfer_id"]})[1]["status"] == "REJECTED"
    assert bank.balance(src) == 2_000_000


@pytest.mark.scenario("T19")
def test_fraud_service_failure_prevents_posting(bank):
    c = bank.customer()
    src, dst = bank.account(c, opening_minor=50_000), bank.account(c)

    def down(_request):
        raise ConnectionError("fraud service timeout")

    clients.OVERRIDES["fraud"] = down
    status, body = bank.transfer(c, src, dst, 1_000)
    assert status == 503 and body["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    assert body["transfer"]["status"] == "FAILED" and body["transfer"]["reason_code"] == "FRAUD_SCREENING_UNAVAILABLE"
    assert bank.balance(src) == 50_000 and bank.balance(dst) == 0


def test_fraud_fault_injection_flag_fails_closed(bank, monkeypatch):
    monkeypatch.setenv("FRAUD_FAULT_INJECTION", "unavailable")
    c = bank.customer()
    src, dst = bank.account(c, opening_minor=50_000), bank.account(c)
    assert bank.transfer(c, src, dst, 1_000)[0] == 503
    assert bank.balance(src) == 50_000


def test_fault_injection_is_ignored_outside_local_and_dev(bank, monkeypatch):
    monkeypatch.setenv("FRAUD_FAULT_INJECTION", "unavailable")
    monkeypatch.setenv("ENVIRONMENT", "prod")
    c = bank.customer()
    src, dst = bank.account(c, opening_minor=50_000), bank.account(c)
    assert bank.transfer(c, src, dst, 1_000)[0] == 201


def test_ambiguous_ledger_failure_is_resumable_with_same_key(bank):
    """A ledger timeout leaves the transfer APPROVED_FOR_POSTING; a retry resumes it."""

    import uuid

    c = bank.customer()
    src, dst = bank.account(c, opening_minor=50_000), bank.account(c)
    calls = {"n": 0}
    from services.ledger import handler as ledger_handler

    def flaky(request):
        if request["action"] == "post_transfer" and calls["n"] == 0:
            calls["n"] += 1
            ledger_handler.internal(request)  # the posting commits...
            raise TimeoutError("...but the response is lost")
        return ledger_handler.internal(request)

    clients.OVERRIDES["ledger"] = flaky
    key = uuid.uuid4().hex
    status, body = bank.transfer(c, src, dst, 1_000, key=key)
    assert status == 503
    status, body = bank.transfer(c, src, dst, 1_000, key=key)
    assert status == 201 and body["status"] == "COMPLETED"
    assert bank.balance(src) == 49_000 and bank.balance(dst) == 1_000


def test_resume_posting_action_for_stuck_transfers(bank):
    from services.transfer.handler import _transition, resume_posting

    c = bank.customer()
    src, dst = bank.account(c, opening_minor=50_000), bank.account(c)
    clients.OVERRIDES["ledger"] = lambda _r: (_ for _ in ()).throw(DependencyUnavailableError("down"))
    status, _body = bank.transfer(c, src, dst, 1_000)
    assert status == 503
    clients.OVERRIDES.clear()
    tid = next(iter(bank.scan("transfers")))["transfer_id"]
    assert resume_posting({"transfer_id": tid})["status"] == "COMPLETED"
    assert bank.balance(dst) == 1_000
    with pytest.raises(Exception):
        _transition(tid, "APPROVED_FOR_POSTING", "FAILED")


def test_unusual_activity_flag_raises_risk(bank):
    from services.fraud.handler import set_flag

    c = bank.customer()
    src, dst = bank.account(c, opening_minor=500_000), bank.account(c)
    set_flag({"customer_id": c["customer_id"], "unusual_activity": True})
    status, _ = bank.transfer(c, src, dst, 100_000)  # 30 alone stays approved
    assert status == 201
    set_flag({"customer_id": c["customer_id"], "unusual_activity": True})
    status, _body = bank.transfer(c, src, dst, 300_000)  # 30 + 20 (new account, >= 2,500)
    assert status == 202
