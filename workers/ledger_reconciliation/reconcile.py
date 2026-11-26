"""Pure ledger reconciliation logic (no I/O) — easy to test against tampering.

Checks (docs/database-design.md#reconciliation):

R1  Each account's authoritative balance equals the sum of its entries.
R2  Each journal balances (total debits == total credits).
R3  Each journal header has exactly one entry per line and vice versa.
R4  Total assets equal total customer liabilities (accounting equation).
R5  No account has a negative balance.
R6  Every COMPLETED transfer has a TRANSFER journal and vice versa.
R7  No transfer has been APPROVED_FOR_POSTING for longer than the threshold.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from shared.ids import parse_iso

STUCK_AFTER = timedelta(minutes=5)


def reconcile(ledger_items: list[dict[str, Any]], transfers: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    balances: dict[str, dict[str, Any]] = {}
    entry_sums: dict[str, int] = defaultdict(int)
    entries_by_journal: dict[str, list[dict[str, Any]]] = defaultdict(list)
    journals: dict[str, dict[str, Any]] = {}
    for item in ledger_items:
        sk = item["SK"]
        if sk == "BALANCE":
            balances[item["account_id"]] = item
        elif sk.startswith("ENTRY#"):
            account_id = item["PK"].removeprefix("ACCOUNT#")
            entry_sums[account_id] += int(item["signed_amount_minor"])
            entries_by_journal[item["journal_id"]].append({**item, "account_id": account_id})
        elif sk == "HEADER":
            journals[item["journal_id"]] = item

    discrepancies: list[dict[str, Any]] = []

    for account_id, bal in balances.items():
        expected = entry_sums.get(account_id, 0)
        if int(bal["available_balance_minor"]) != expected:
            discrepancies.append(
                {
                    "check": "R1",
                    "account_id": account_id,
                    "balance_minor": int(bal["available_balance_minor"]),
                    "entries_sum_minor": expected,
                }
            )
        if int(bal["available_balance_minor"]) < 0:
            discrepancies.append({"check": "R5", "account_id": account_id, "balance_minor": int(bal["available_balance_minor"])})
    for account_id in set(entry_sums) - set(balances):
        discrepancies.append({"check": "R1", "account_id": account_id, "detail": "entries without balance record"})

    for journal_id, header in journals.items():
        debits = sum(int(ln["amount_minor"]) for ln in header["lines"] if ln["side"] == "D")
        credits = sum(int(ln["amount_minor"]) for ln in header["lines"] if ln["side"] == "C")
        if debits != credits:
            discrepancies.append({"check": "R2", "journal_id": journal_id, "debits_minor": debits, "credits_minor": credits})
        entries = entries_by_journal.get(journal_id, [])
        expected_lines = sorted((ln["account_id"], ln["side"], int(ln["amount_minor"])) for ln in header["lines"])
        actual_lines = sorted((e["account_id"], e["side"], int(e["amount_minor"])) for e in entries)
        if expected_lines != actual_lines:
            discrepancies.append({"check": "R3", "journal_id": journal_id, "detail": "entries do not match journal lines"})
        entry_debits = sum(int(e["amount_minor"]) for e in entries if e["side"] == "D")
        entry_credits = sum(int(e["amount_minor"]) for e in entries if e["side"] == "C")
        if entry_debits != entry_credits:
            discrepancies.append({"check": "R2", "journal_id": journal_id, "detail": "posted entries are unbalanced"})
    for journal_id in set(entries_by_journal) - set(journals):
        discrepancies.append({"check": "R3", "journal_id": journal_id, "detail": "entries without journal header"})

    assets = sum(int(b["available_balance_minor"]) for b in balances.values() if b["account_class"] == "ASSET")
    liabilities = sum(int(b["available_balance_minor"]) for b in balances.values() if b["account_class"] == "LIABILITY")
    if assets != liabilities:
        discrepancies.append({"check": "R4", "assets_minor": assets, "liabilities_minor": liabilities})

    transfer_journals = {j for j, h in journals.items() if h["journal_type"] == "TRANSFER"}
    completed = {t["transfer_id"] for t in transfers if t["status"] == "COMPLETED"}
    for tid in completed - transfer_journals:
        discrepancies.append({"check": "R6", "transfer_id": tid, "detail": "COMPLETED transfer without journal"})
    for tid in transfer_journals - completed:
        discrepancies.append({"check": "R6", "transfer_id": tid, "detail": "journal without COMPLETED transfer"})

    stuck = [
        t["transfer_id"]
        for t in transfers
        if t["status"] in {"APPROVED_FOR_POSTING", "SCREENING"} and now - parse_iso(t["updated_at"]) > STUCK_AFTER
    ]
    for tid in stuck:
        discrepancies.append({"check": "R7", "transfer_id": tid, "detail": "transfer stuck before posting"})

    return {
        "status": "BALANCED" if not discrepancies else "DISCREPANCIES_FOUND",
        "accounts_checked": len(balances),
        "journals_checked": len(journals),
        "transfers_checked": len(transfers),
        "total_assets_minor": assets,
        "total_liabilities_minor": liabilities,
        "discrepancy_count": len(discrepancies),
        "discrepancies": discrepancies[:200],
    }
