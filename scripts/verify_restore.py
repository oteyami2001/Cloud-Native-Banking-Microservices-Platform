#!/usr/bin/env python3
"""Read-only reconciliation of point-in-time-restored ledger tables (T29).

Unlike the scheduled reconciliation job, this script writes nothing: no
evidence object, no audit row, no outbox event. That matters because a
restored copy must be validated *before* anything is switched over, and a
validation run must not publish events into the live platform.

Usage (AWS CloudShell, Python 3.11+ with boto3):
    python3.11 scripts/verify_restore.py \
        --ledger-table novabank-dev-ledger-t29 \
        --transfers-table novabank-dev-transfers-t29 \
        --as-of 2026-11-27T05:10:00Z

``--as-of`` is the restore timestamp; it is used as "now" for the stuck-transfer
check (R7) so a transfer that was legitimately in flight at that instant is
judged relative to the restore point, not to today.

Exit code 0 when the restored copy is BALANCED, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared import aws
from workers.ledger_reconciliation.reconcile import reconcile


def scan(table_name: str) -> list[dict[str, Any]]:
    table = aws.table(table_name)
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {"ConsistentRead": True}
    while True:
        page = table.scan(**kwargs)
        items.extend(aws.to_native(page.get("Items", [])))
        if "LastEvaluatedKey" not in page:
            return items
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def mask(account_id: str) -> str:
    return account_id if account_id.startswith("GL-") else f"****{account_id[-4:]}"


def usd(minor: int) -> str:
    """Format integer cents without floating point."""
    sign = "-" if minor < 0 else ""
    dollars, cents = divmod(abs(minor), 100)
    return f"{sign}${dollars:,}.{cents:02d}"


def verify(ledger_table: str, transfers_table: str, as_of: str) -> dict[str, Any]:
    ledger_items = scan(ledger_table)
    transfers = [i for i in scan(transfers_table) if i.get("SK") == "METADATA"]
    report = reconcile(ledger_items, transfers, datetime.fromisoformat(as_of))
    report["balances"] = {
        mask(i["account_id"]): int(i["available_balance_minor"])
        for i in sorted(ledger_items, key=lambda i: i.get("account_id", ""))
        if i.get("SK") == "BALANCE"
    }
    report["as_of"] = as_of
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--ledger-table", required=True)
    p.add_argument("--transfers-table", required=True)
    p.add_argument("--as-of", required=True, help="restore timestamp, ISO-8601 UTC")
    args = p.parse_args(argv)

    report = verify(args.ledger_table, args.transfers_table, args.as_of)
    summary = {k: v for k, v in report.items() if k not in {"discrepancies", "balances"}}
    print(json.dumps(summary, indent=2))
    print("Balances at restore point:")
    for account, minor in report["balances"].items():
        print(f"  {account:<14} {usd(minor):>14}")
    for d in report["discrepancies"]:
        print("DISCREPANCY", json.dumps(d))
    return 0 if report["status"] == "BALANCED" else 1


if __name__ == "__main__":
    sys.exit(main())
