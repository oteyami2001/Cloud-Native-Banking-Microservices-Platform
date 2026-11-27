"""verify_restore.py validates a restored copy without writing anything."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def _item_counts(aws, tables) -> dict[str, int]:
    t = tables()
    return {name: aws.table(getattr(t, name)).scan(Select="COUNT")["Count"] for name in ("audit", "outbox")}


def test_restored_copy_is_reconciled_read_only(bank, capsys):
    import verify_restore

    from shared import aws
    from shared.config import tables

    a = bank.customer()
    a1, a2 = bank.account(a, opening_minor=480_000), bank.account(a)
    bank.transfer(a, a1, a2, 25_000)
    before = _item_counts(aws, tables)

    t = tables()
    code = verify_restore.main(["--ledger-table", t.ledger, "--transfers-table", t.transfers, "--as-of", "2026-11-27T05:10:00Z"])

    out = capsys.readouterr().out
    assert code == 0
    assert '"status": "BALANCED"' in out
    assert "$4,550.00" in out and "$250.00" in out
    assert _item_counts(aws, tables) == before  # nothing written


def test_usd_formats_integer_cents():
    import verify_restore

    assert verify_restore.usd(2_535_000) == "$25,350.00"
    assert verify_restore.usd(-5) == "-$0.05"
