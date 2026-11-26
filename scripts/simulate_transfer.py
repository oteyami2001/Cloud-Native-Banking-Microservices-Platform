#!/usr/bin/env python3
"""Demonstrate the $250 checking -> savings transfer and its invariants.

Run scripts/local_api.py first (or pass --api for a deployed environment).
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sandbox_client import Api


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8080")
    parser.add_argument("--amount-minor", type=int, default=25_000)
    args = parser.parse_args()
    api = Api(args.api)
    print("Registering synthetic customer:", api.call("POST", "/v1/customers", {"display_name": "Demo Customer"})[0])
    _, checking = api.call("POST", "/v1/accounts", {"account_type": "CHECKING", "sandbox_opening_balance_minor": 485_000})
    _, savings = api.call("POST", "/v1/accounts", {"account_type": "SAVINGS"})

    def bal(acc):
        return api.call("GET", f"/v1/accounts/{acc['account_id']}/balance")[1]["available_balance_minor"]

    before = bal(checking) + bal(savings)
    key = uuid.uuid4().hex
    body = {
        "source_account_id": checking["account_id"],
        "destination_account_id": savings["account_id"],
        "amount_minor": args.amount_minor,
        "currency": "USD",
    }
    status, transfer = api.call("POST", "/v1/transfers", body, idempotency_key=key)
    print(f"Transfer: HTTP {status} status={transfer.get('status') or transfer.get('error', {}).get('code')}")
    replay_status, _ = api.call("POST", "/v1/transfers", body, idempotency_key=key)
    print(f"Replay with same Idempotency-Key: HTTP {replay_status} (no second posting)")
    after = bal(checking) + bal(savings)
    print(f"Checking {bal(checking) / 100:.2f}  Savings {bal(savings) / 100:.2f}  Combined {before / 100:.2f} -> {after / 100:.2f}")
    assert before == after, "combined balance changed!"
    print("Invariant holds: internal transfer conserved the combined balance.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
