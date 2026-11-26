#!/usr/bin/env python3
"""Create the synthetic general-ledger funding account (GL-1000).

Idempotent. All customer demo balances are then created through documented
opening-balance journals (Dr GL-1000 / Cr deposit), never by direct writes.
Requires credentials for the target environment's ledger table (or a local endpoint).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.ledger.engine import Ledger
from shared.config import GL_SYNTHETIC_FUNDING_ACCOUNT, tables

if __name__ == "__main__":
    print(f"Ledger table: {tables().ledger}")
    print(Ledger().open_account(GL_SYNTHETIC_FUNDING_ACCOUNT, customer_id=None, currency="USD", account_class="ASSET"))
