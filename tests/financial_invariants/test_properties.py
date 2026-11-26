"""Property-based tests of the seven financial invariants (master prompt §10)."""

from __future__ import annotations

import uuid

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from services.ledger.engine import Ledger, Line
from shared.config import GL_SYNTHETIC_FUNDING_ACCOUNT
from shared.errors import BankingError
from workers.ledger_reconciliation.reconcile import reconcile

operations = st.lists(
    st.tuples(st.integers(0, 3), st.integers(0, 3), st.integers(1, 60_000), st.booleans()),
    min_size=1,
    max_size=25,
)


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(ops=operations, openings=st.lists(st.integers(0, 100_000), min_size=4, max_size=4))
def test_random_operation_sequences_preserve_invariants(aws_env, ops, openings):
    from datetime import UTC, datetime

    from tests.support import Bank

    Bank()  # ensures GL-1000 exists (idempotent)
    ledger = Ledger()
    owner = f"CUS-{uuid.uuid4().hex[:20].upper()}"
    accounts = [f"ACC-{uuid.uuid4().hex[:20].upper()}" for _ in range(4)]
    for acc, opening in zip(accounts, openings, strict=True):
        ledger.open_account(acc, customer_id=owner, currency="USD")
        if opening:
            ledger.post_opening_balance(acc, opening, "USD", None)

    def balances():
        return [ledger.get_balance(a)["available_balance_minor"] for a in accounts]

    for i, (s, d, amount, replay) in enumerate(ops):
        before = balances()
        journal_id = f"J-{i}"
        try:
            ledger.post_journal(
                journal_id=journal_id,
                journal_type="TEST",
                currency="USD",
                lines=[Line(accounts[s], "D", amount), Line(accounts[d], "C", amount)],
                description="prop",
                correlation_id=None,
            )
            if replay:  # invariant 4: replays never double post
                ledger.post_journal(
                    journal_id=journal_id,
                    journal_type="TEST",
                    currency="USD",
                    lines=[Line(accounts[s], "D", amount), Line(accounts[d], "C", amount)],
                    description="prop",
                    correlation_id=None,
                )
            after = balances()
            assert sum(after) == sum(before)  # invariant 1: conservation
            assert after[s] == before[s] - amount and after[d] == before[d] + amount
        except BankingError:
            assert balances() == before  # invariant 5: failures change nothing
        assert min(balances()) >= 0  # invariant 3 / 6: never negative

    from shared import aws
    from shared.config import tables

    items = aws.to_native(aws.table(tables().ledger).scan(ConsistentRead=True)["Items"])
    report = reconcile(items, [], datetime.now(UTC))
    assert report["status"] == "BALANCED", report  # invariants 2 and 7
    gl = ledger.get_balance(GL_SYNTHETIC_FUNDING_ACCOUNT)["available_balance_minor"]
    assert report["total_assets_minor"] == gl
