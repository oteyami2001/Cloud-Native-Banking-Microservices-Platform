"""Authentication, object-level authorization and separation of duties."""

from __future__ import annotations

import time
import uuid

import pytest

from tests.support import ADMIN_SCOPES, claims


@pytest.mark.scenario("T03")
@pytest.mark.parametrize(
    "bad_claims",
    [
        None,  # no authorizer context at all
        {"sub": ""},
        claims("x", exp=str(int(time.time()) - 10)),
        claims("x", token_use="id"),
        claims("x", exp="not-a-number"),
    ],
)
def test_invalid_or_expired_tokens_are_rejected(bank, bad_claims):
    status, body = bank.call("GET /v1/accounts", bad_claims)
    assert status == 401 and body["error"]["code"] == "UNAUTHENTICATED"


def test_issuer_and_audience_are_rechecked(bank, monkeypatch):
    monkeypatch.setenv("EXPECTED_ISSUER", "https://cognito-idp.us-east-2.amazonaws.com/us-east-2_EXAMPLE")
    monkeypatch.setenv("ALLOWED_CLIENT_IDS", "client-a")
    good = claims("s", iss="https://cognito-idp.us-east-2.amazonaws.com/us-east-2_EXAMPLE", client_id="client-a")
    assert bank.call("GET /v1/accounts", good)[0] == 403  # authenticated; no profile yet
    assert bank.call("GET /v1/accounts", {**good, "iss": "https://evil.example"})[0] == 401
    assert bank.call("GET /v1/accounts", {**good, "client_id": "client-b"})[0] == 401


def test_missing_scope_is_forbidden(bank):
    c = bank.customer()
    read_only = {**c["claims"], "scope": "novabank/read"}
    status, body = bank.call("POST /v1/accounts", read_only, body={"account_type": "CHECKING"})
    assert status == 403 and body["error"]["details"]["required_scope"] == "novabank/write"


@pytest.mark.scenario("T04")
def test_customer_cannot_access_another_customers_account(bank):
    alice, mallory = bank.customer(), bank.customer()
    acc = bank.account(alice, opening_minor=10_000)
    for route in ("GET /v1/accounts/{id}", "GET /v1/accounts/{id}/balance", "GET /v1/accounts/{id}/transactions"):
        status, body = bank.call(route, mallory["claims"], path={"id": acc})
        # 404 rather than 403 so account ids cannot be enumerated.
        assert status == 404 and body["error"]["code"] == "NOT_FOUND", route


def test_customer_cannot_debit_another_customers_account(bank):
    alice, mallory = bank.customer(), bank.customer()
    victim = bank.account(alice, opening_minor=10_000)
    mine = bank.account(mallory)
    status, _body = bank.transfer(mallory, victim, mine, 5_000)
    assert status == 404
    assert bank.balance(victim) == 10_000 and bank.balance(mine) == 0


def test_customer_cannot_view_another_customers_transfer(bank):
    alice, mallory = bank.customer(), bank.customer()
    a1, a2 = bank.account(alice, opening_minor=10_000), bank.account(alice)
    transfer_id = bank.transfer(alice, a1, a2, 100)[1]["transfer_id"]
    assert bank.call("GET /v1/transfers/{id}", mallory["claims"], path={"id": transfer_id})[0] == 404


def test_tampered_pagination_cursor_cannot_cross_partitions(bank):
    import base64
    import json

    alice, mallory = bank.customer(), bank.customer()
    acc = bank.account(alice, opening_minor=10_000)
    forged = base64.urlsafe_b64encode(json.dumps({"PK": f"ACCOUNT#{acc}", "SK": "ENTRY#9"}).encode()).decode()
    mine = bank.account(mallory)
    status, body = bank.call("GET /v1/accounts/{id}/transactions", mallory["claims"], path={"id": mine}, query={"cursor": forged})
    assert status == 400 and body["error"]["code"] == "VALIDATION_ERROR"


def test_identity_in_body_is_rejected_mass_assignment(bank):
    c = bank.customer()
    status, body = bank.call("POST /v1/accounts", c["claims"], body={"account_type": "CHECKING", "customer_id": "CUS-ATTACKER"})
    assert status == 400 and "customer_id" in body["error"]["details"]["fields"]


@pytest.mark.scenario("T17")
def test_customer_cannot_approve_held_transfer_or_supply_fraud_approval(bank):
    c = bank.customer()
    src, dst = bank.account(c, opening_minor=2_000_000), bank.account(bank.customer())
    status, held = bank.transfer(c, src, dst, 600_000)
    assert status == 202 and held["status"] == "PENDING_REVIEW"
    # A customer token (no admin scope / reviewer group) cannot approve.
    status, body = bank.call("POST /v1/admin/transfers/{id}/approve", c["claims"], path={"id": held["transfer_id"]})
    assert status == 403
    # Even with a forged admin scope, the reviewer group is required.
    forged = {**c["claims"], "scope": ADMIN_SCOPES}
    assert bank.call("POST /v1/admin/transfers/{id}/approve", forged, path={"id": held["transfer_id"]})[0] == 403
    # A client-supplied fraud decision is not part of the contract.
    status, body = bank.call(
        "POST /v1/transfers",
        c["claims"],
        body={
            "source_account_id": src,
            "destination_account_id": dst,
            "amount_minor": 600_000,
            "currency": "USD",
            "fraud_decision": "APPROVED",
        },
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert status == 400 and "fraud_decision" in body["error"]["details"]["fields"]
    assert bank.balance(src) == 2_000_000


def test_reviewer_cannot_approve_own_transfer_separation_of_duties(bank):
    sub = str(uuid.uuid4())
    dual = claims(sub, scopes=ADMIN_SCOPES, groups="[customers fraud-reviewers]")
    assert bank.call("POST /v1/customers", dual, body={"display_name": "Insider"})[0] == 201
    me = {"claims": dual}
    src, dst = bank.account(me, opening_minor=2_000_000), bank.account(bank.customer())
    held = bank.transfer(me, src, dst, 600_000)[1]
    status, body = bank.call("POST /v1/admin/transfers/{id}/approve", dual, path={"id": held["transfer_id"]})
    assert status == 403 and body["error"]["code"] == "SEPARATION_OF_DUTIES"
    assert bank.balance(src) == 2_000_000


def test_admin_endpoints_require_reviewer_or_auditor(bank):
    c = bank.customer()
    assert bank.call("GET /v1/admin/fraud-alerts", c["claims"])[0] == 403
    assert bank.call("GET /v1/admin/reconciliation", c["claims"])[0] == 403
    auditor = claims(str(uuid.uuid4()), scopes=ADMIN_SCOPES, groups="[auditors]")
    assert bank.call("GET /v1/admin/reconciliation", auditor)[0] == 200
    assert bank.call("GET /v1/admin/fraud-alerts", auditor)[0] == 403


def test_errors_never_leak_internals(bank, monkeypatch):
    import services.account.handler as account

    c = bank.customer()

    def boom(*_a, **_k):
        raise RuntimeError("secret internal detail arn:aws:dynamodb:...")

    monkeypatch.setattr(account, "customer_id_for", boom)
    status, body = bank.call("GET /v1/accounts", c["claims"])
    assert status == 500 and body["error"] == {
        "code": "INTERNAL_ERROR",
        "message": "Internal error",
        "correlation_id": body["error"]["correlation_id"],
    }


def test_responses_carry_security_headers_and_correlation_id(bank):
    from services.account.handler import handler
    from tests.support import api_event

    c = bank.customer()
    resp = handler(api_event("GET /v1/accounts", claims_=c["claims"], headers={"X-Correlation-Id": "corr-12345678"}))
    assert resp["headers"]["x-correlation-id"] == "corr-12345678"
    assert resp["headers"]["cache-control"] == "no-store"
    assert resp["headers"]["x-content-type-options"] == "nosniff"


def test_unknown_route_returns_404(bank):
    from services.account.handler import handler
    from tests.support import api_event

    assert handler(api_event("DELETE /v1/accounts/{id}", claims_=claims("x")))["statusCode"] == 404


def test_internal_invocation_rejects_unknown_actions(aws_env):
    from services.ledger.handler import handler

    assert handler({"action": "drop_tables", "payload": {}})["ok"] is False


def test_logs_redact_sensitive_fields():
    from shared.logging import REDACTED, redact

    out = redact({"Authorization": "Bearer abc", "nested": {"email": "x@example.com", "ok": 1}, "list": [{"password": "p"}]})
    assert out == {"Authorization": REDACTED, "nested": {"email": REDACTED, "ok": 1}, "list": [{"password": REDACTED}]}
