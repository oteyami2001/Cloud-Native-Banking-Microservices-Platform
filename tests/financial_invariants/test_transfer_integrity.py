"""Financial integrity: validation, atomicity, idempotency, reconciliation."""

from __future__ import annotations

import uuid

import pytest
from botocore.exceptions import ClientError

from services.ledger.engine import Ledger, Line
from shared.errors import ValidationError
from tests.support import claims


def total_customer_balance(bank, *accounts):
    return sum(bank.balance(a) for a in accounts)


@pytest.mark.scenario("T08")
def test_insufficient_funds_is_rejected_without_posting(bank):
    c = bank.customer()
    src, dst = bank.account(c, opening_minor=10_000), bank.account(c)
    status, body = bank.transfer(c, src, dst, 10_001)
    assert status == 422 and body["error"]["code"] == "INSUFFICIENT_FUNDS"
    assert body["transfer"]["status"] == "REJECTED"
    assert bank.balance(src) == 10_000 and bank.balance(dst) == 0
    assert not [i for i in bank.scan("ledger") if i["SK"] == "HEADER" and i["journal_type"] == "TRANSFER"]


@pytest.mark.scenario("T09")
@pytest.mark.parametrize("amount", [0, -1, -25_000, 1.5, 250.0, "250.00", True, None, 100_000_001])
def test_zero_negative_malformed_and_excessive_amounts_are_rejected(bank, amount):
    c = bank.customer()
    src, dst = bank.account(c, opening_minor=10_000), bank.account(c)
    status, body = bank.transfer(c, src, dst, amount)
    assert status == 400 and body["error"]["code"] == "VALIDATION_ERROR"
    assert bank.balance(src) == 10_000


def test_float_json_numbers_are_rejected_at_parse_time(bank):
    c = bank.customer()
    src, dst = bank.account(c, opening_minor=10_000), bank.account(c)
    raw = f'{{"source_account_id":"{src}","destination_account_id":"{dst}","amount_minor":100.0,"currency":"USD"}}'
    status, body = bank.call("POST /v1/transfers", c["claims"], raw_body=raw, headers={"Idempotency-Key": uuid.uuid4().hex})
    assert status == 400 and "Floating-point" in body["error"]["message"]


@pytest.mark.scenario("T10")
def test_unsupported_currency_and_currency_mismatch_are_rejected(bank):
    c = bank.customer()
    src, dst = bank.account(c, opening_minor=10_000), bank.account(c)
    assert bank.transfer(c, src, dst, 100, currency="EUR")[0] == 400
    # Ledger-level guard: a journal in another currency cannot touch USD accounts.
    from shared import money

    money.SUPPORTED_CURRENCIES["EUR"] = 2
    try:
        with pytest.raises(Exception) as exc:
            Ledger().post_journal(
                journal_id="J-EUR",
                journal_type="TEST",
                currency="EUR",
                lines=[Line(src, "D", 100), Line(dst, "C", 100)],
                description="x",
                correlation_id=None,
            )
        assert getattr(exc.value, "code", "") == "CURRENCY_MISMATCH"
    finally:
        money.SUPPORTED_CURRENCIES.pop("EUR")
    assert bank.balance(src) == 10_000


@pytest.mark.scenario("T13")
def test_self_transfer_is_rejected(bank):
    c = bank.customer()
    src = bank.account(c, opening_minor=10_000)
    status, body = bank.transfer(c, src, src, 100)
    assert status == 400 and "different" in body["error"]["message"]


@pytest.mark.scenario("T11")
def test_duplicate_request_does_not_post_twice(bank):
    c = bank.customer()
    src, dst = bank.account(c, opening_minor=100_000), bank.account(c)
    key = uuid.uuid4().hex
    first = bank.transfer(c, src, dst, 25_000, key=key)
    second = bank.transfer(c, src, dst, 25_000, key=key)
    assert first == second and first[0] == 201
    assert bank.balance(src) == 75_000 and bank.balance(dst) == 25_000
    assert len([i for i in bank.scan("ledger") if i["SK"] == "HEADER" and i["journal_type"] == "TRANSFER"]) == 1


def test_idempotency_key_reused_with_different_payload_is_rejected(bank):
    c = bank.customer()
    src, dst = bank.account(c, opening_minor=100_000), bank.account(c)
    key = uuid.uuid4().hex
    assert bank.transfer(c, src, dst, 1_000, key=key)[0] == 201
    status, body = bank.transfer(c, src, dst, 2_000, key=key)
    assert status == 422 and body["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert bank.balance(src) == 99_000


def test_idempotency_keys_are_scoped_to_the_customer(bank):
    a, b = bank.customer(), bank.customer()
    a1, a2 = bank.account(a, opening_minor=10_000), bank.account(a)
    b1, b2 = bank.account(b, opening_minor=10_000), bank.account(b)
    key = uuid.uuid4().hex
    assert bank.transfer(a, a1, a2, 100, key=key)[0] == 201
    assert bank.transfer(b, b1, b2, 100, key=key)[0] == 201


def test_idempotency_key_is_required_and_validated(bank):
    c = bank.customer()
    src, dst = bank.account(c, opening_minor=10_000), bank.account(c)
    body = {"source_account_id": src, "destination_account_id": dst, "amount_minor": 1, "currency": "USD"}
    assert bank.call("POST /v1/transfers", c["claims"], body=body)[0] == 400
    assert bank.call("POST /v1/transfers", c["claims"], body=body, headers={"Idempotency-Key": "short"})[0] == 400


def test_ledger_posting_is_idempotent_on_journal_id(bank):
    c = bank.customer()
    acc = bank.account(c)
    ledger = Ledger()
    first = ledger.post_opening_balance(acc, 5_000, "USD", None)
    second = ledger.post_opening_balance(acc, 5_000, "USD", None)
    assert not first.replayed and second.replayed
    assert bank.balance(acc) == 5_000
    with pytest.raises(Exception) as exc:
        ledger.post_opening_balance(acc, 6_000, "USD", None)
    assert exc.value.code == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.scenario("T14")
def test_failed_atomic_write_produces_no_partial_posting(bank, monkeypatch):
    """Inject a failure into one item of the transaction (the outbox put)."""

    c = bank.customer()
    src, dst = bank.account(c, opening_minor=50_000), bank.account(c)
    before = {k: len(bank.scan(k)) for k in ("ledger", "outbox", "idempotency")}

    import services.ledger.engine as engine

    original = engine.Ledger._build_items

    def sabotage(self, *args, **kwargs):
        items = original(self, *args, **kwargs)
        outbox = next(i for i in items if "Put" in i and i["Put"]["TableName"].endswith("outbox"))
        outbox["Put"]["ConditionExpression"] = "attribute_exists(PK)"  # always fails
        return items

    monkeypatch.setattr(engine.Ledger, "_build_items", sabotage)
    ledger = Ledger()
    with pytest.raises(Exception):
        ledger.post_journal(
            journal_id="J-ATOMIC",
            journal_type="TRANSFER",
            currency="USD",
            lines=[Line(src, "D", 10_000), Line(dst, "C", 10_000)],
            description="atomic",
            correlation_id=None,
        )
    assert bank.balance(src) == 50_000 and bank.balance(dst) == 0
    assert {k: len(bank.scan(k)) for k in ("ledger", "outbox", "idempotency")} == before


def test_unbalanced_or_degenerate_journals_are_refused(bank):
    c = bank.customer()
    a, b = bank.account(c, opening_minor=1_000), bank.account(c)
    ledger = Ledger()
    for lines in (
        [Line(a, "D", 10), Line(b, "C", 9)],
        [Line(a, "D", 10)],
        [Line(a, "D", 10), Line(a, "C", 10)],
        [Line(a, "X", 10), Line(b, "C", 10)],
    ):
        with pytest.raises(ValidationError):
            ledger.post_journal(
                journal_id=f"J-{uuid.uuid4().hex[:6]}",
                journal_type="TEST",
                currency="USD",
                lines=lines,
                description="x",
                correlation_id=None,
            )


def test_frozen_account_cannot_send_or_receive(bank):
    c = bank.customer()
    src, dst = bank.account(c, opening_minor=10_000), bank.account(c)
    Ledger().set_status(dst, "FROZEN")
    # Account metadata is still ACTIVE, so the ledger's own condition is what stops it.
    status, body = bank.transfer(c, src, dst, 1_000)
    assert status == 422 and body["error"]["code"] == "ACCOUNT_NOT_ACTIVE"
    assert bank.balance(src) == 10_000


def test_reversal_uses_compensating_entries_not_deletes(bank):
    c = bank.customer()
    src, dst = bank.account(c, opening_minor=10_000), bank.account(c)
    tid = bank.transfer(c, src, dst, 4_000)[1]["transfer_id"]
    entries_before = len([i for i in bank.scan("ledger") if i["SK"].startswith("ENTRY#")])
    Ledger().reverse_transfer(tid, reason="customer dispute (synthetic)", operator="ops-1", correlation_id=None)
    assert bank.balance(src) == 10_000 and bank.balance(dst) == 0
    assert len([i for i in bank.scan("ledger") if i["SK"].startswith("ENTRY#")]) == entries_before + 2


@pytest.mark.scenario("T15")
def test_reconciliation_balances_after_activity(bank):
    from workers.ledger_reconciliation.handler import run

    a, b = bank.customer(), bank.customer()
    a1, a2, b1 = bank.account(a, opening_minor=300_000), bank.account(a), bank.account(b, opening_minor=50_000)
    bank.transfer(a, a1, a2, 25_000)
    bank.transfer(a, a1, b1, 10_000)
    bank.transfer(b, b1, a2, 60_001)  # rejected: insufficient funds
    report = run()
    assert report["status"] == "BALANCED", report["discrepancies"]
    assert report["total_assets_minor"] == report["total_liabilities_minor"] == 350_000
    # Report is stored as evidence and visible to auditors.
    auditor = claims(str(uuid.uuid4()), scopes="novabank/admin", groups="[auditors]")
    status, body = bank.call("GET /v1/admin/reconciliation", auditor)
    assert status == 200 and body["items"][0]["status"] == "BALANCED"


def test_reconciliation_detects_tampering(bank):
    from shared import aws
    from shared.config import tables
    from workers.ledger_reconciliation.handler import run

    c = bank.customer()
    acc = bank.account(c, opening_minor=10_000)
    # Simulate an untracked write that bypasses the ledger (what the IAM model forbids).
    aws.table(tables().ledger).update_item(
        Key={"PK": f"ACCOUNT#{acc}", "SK": "BALANCE"},
        UpdateExpression="SET available_balance_minor = :v",
        ExpressionAttributeValues={":v": 999_999},
    )
    report = run()
    assert report["status"] == "DISCREPANCIES_FOUND"
    assert {d["check"] for d in report["discrepancies"]} >= {"R1", "R4"}


def test_non_integral_numbers_in_storage_are_refused():
    from decimal import Decimal

    from shared.aws import to_native

    assert to_native({"a": Decimal("10")}) == {"a": 10}
    with pytest.raises(ValueError):
        to_native({"a": Decimal("10.5")})


def test_unexpected_dynamodb_errors_propagate(bank, monkeypatch):
    c = bank.customer()
    a, b = bank.account(c, opening_minor=1_000), bank.account(c)
    ledger = Ledger()

    def fail(**_):
        raise ClientError({"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "x"}}, "TransactWriteItems")

    monkeypatch.setattr(ledger.client, "transact_write_items", fail)
    with pytest.raises(ClientError):
        ledger.post_journal(
            journal_id="J-ERR",
            journal_type="TEST",
            currency="USD",
            lines=[Line(a, "D", 1), Line(b, "C", 1)],
            description="x",
            correlation_id=None,
        )
