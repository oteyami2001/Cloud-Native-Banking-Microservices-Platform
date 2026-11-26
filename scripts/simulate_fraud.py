#!/usr/bin/env python3
"""Exercise fraud screening: approved, held for review (then approved), rejected."""

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
    args = parser.parse_args()
    alice, bob = Api(args.api), Api(args.api)
    reviewer = Api(args.api, groups="fraud-reviewers")
    alice.call("POST", "/v1/customers", {"display_name": "Alice Synthetic"})
    bob.call("POST", "/v1/customers", {"display_name": "Bob Synthetic"})
    src = alice.call("POST", "/v1/accounts", {"account_type": "CHECKING", "sandbox_opening_balance_minor": 2_500_000})[1]["account_id"]
    dst = bob.call("POST", "/v1/accounts", {"account_type": "CHECKING"})[1]["account_id"]
    for amount in (20_000, 600_000, 950_000):
        status, out = alice.call(
            "POST",
            "/v1/transfers",
            {"source_account_id": src, "destination_account_id": dst, "amount_minor": amount, "currency": "USD"},
            idempotency_key=uuid.uuid4().hex,
        )
        state = out.get("status") or out.get("transfer", {}).get("status")
        print(f"${amount / 100:,.2f}: HTTP {status} -> {state}")
        if state == "PENDING_REVIEW":
            _, alerts = reviewer.call("GET", "/v1/admin/fraud-alerts")
            alert = alerts["items"][0]
            print(f"   alert score={alert['risk_score']} rules={alert['triggered_rules']} policy={alert['policy_version']}")
            print("   customer self-approval:", alice.call("POST", f"/v1/admin/transfers/{out['transfer_id']}/approve")[0])
            status, approved = reviewer.call(
                "POST", f"/v1/admin/transfers/{out['transfer_id']}/approve", {"reason": "Verified by phone - synthetic"}
            )
            print(f"   reviewer approval: HTTP {status} -> {approved.get('status')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
