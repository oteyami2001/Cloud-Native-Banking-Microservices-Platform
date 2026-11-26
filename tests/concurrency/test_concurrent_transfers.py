"""Concurrent transfers must never overspend an account.

The guarantee comes from the conditional balance update inside the
transaction (``available_balance_minor >= :needed``), not from any in-process
lock. These tests run real threads through the handlers. moto serialises
individual API calls, which mirrors DynamoDB's per-item serialisation of
conditional writes; the live-AWS variant is scripts/simulate_failure.py
``concurrent-overdraw``.
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest


@pytest.mark.scenario("T12")
def test_concurrent_transfers_cannot_overdraw(bank):
    c = bank.customer()
    src = bank.account(c, opening_minor=100_000)  # $1,000
    dests = [bank.account(c) for _ in range(4)]

    def attempt(i):
        return bank.transfer(c, src, dests[i % 4], 30_000)  # $300 each, 10 attempts

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(attempt, range(10)))

    completed = [r for r in results if r[0] == 201]
    rejected = [r for r in results if r[0] != 201]
    assert len(completed) == 3, [r[0] for r in results]
    assert all(r[1]["error"]["code"] in {"INSUFFICIENT_FUNDS", "CONCURRENCY_CONFLICT"} for r in rejected)
    assert bank.balance(src) == 10_000
    assert sum(bank.balance(d) for d in dests) == 90_000


def test_concurrent_duplicate_requests_post_once(bank):
    c = bank.customer()
    src, dst = bank.account(c, opening_minor=100_000), bank.account(c)
    key = uuid.uuid4().hex

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: bank.transfer(c, src, dst, 5_000, key=key), range(8)))

    statuses = sorted(r[0] for r in results)
    assert statuses.count(201) >= 1
    assert set(statuses) <= {201, 409}
    assert bank.balance(src) == 95_000 and bank.balance(dst) == 5_000
    headers = [i for i in bank.scan("ledger") if i["SK"] == "HEADER" and i["journal_type"] == "TRANSFER"]
    assert len(headers) == 1


def test_bidirectional_concurrent_transfers_conserve_money(bank):
    c = bank.customer()
    a, b = bank.account(c, opening_minor=50_000), bank.account(c, opening_minor=50_000)

    def move(i):
        return bank.transfer(c, a, b, 700) if i % 2 else bank.transfer(c, b, a, 300)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(move, range(30)))
    assert bank.balance(a) + bank.balance(b) == 100_000
    assert bank.balance(a) >= 0 and bank.balance(b) >= 0
