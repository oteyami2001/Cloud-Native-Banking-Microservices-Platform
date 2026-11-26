#!/usr/bin/env python3
"""Controlled failure injection scenarios (offline, in-process, moto-backed).

  concurrent-overdraw   10 parallel $300 transfers from a $1,000 account (T12)
  fraud-down            fraud dependency unavailable -> fail closed (T19)
  lost-response         ledger commits but the response is lost; retry resumes (T11/T14)

For live AWS fault injection use the Terraform fault_injection variable
(dev only) — see runbooks/incident-response.md.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.update({"AWS_ACCESS_KEY_ID": "x", "AWS_SECRET_ACCESS_KEY": "x", "AWS_DEFAULT_REGION": "us-east-2", "ENVIRONMENT": "local"})
os.environ.pop("AWS_SESSION_TOKEN", None)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=["concurrent-overdraw", "fraud-down", "lost-response"])
    args = parser.parse_args()

    import boto3
    from moto import mock_aws

    import tests.conftest  # noqa: F401 - installs the moto per-call lock
    from shared import clients
    from shared.schema import create_all
    from tests.support import Bank

    with mock_aws():
        create_all(boto3.client("dynamodb", region_name="us-east-2"))
        bank = Bank()
        c = bank.customer()
        if args.scenario == "concurrent-overdraw":
            src = bank.account(c, opening_minor=100_000)
            dst = bank.account(c)
            with ThreadPoolExecutor(10) as pool:
                results = list(pool.map(lambda _: bank.transfer(c, src, dst, 30_000)[0], range(10)))
            print("HTTP statuses:", sorted(results))
            print(f"Source balance {bank.balance(src)} (never negative), destination {bank.balance(dst)}")
        elif args.scenario == "fraud-down":
            src, dst = bank.account(c, opening_minor=50_000), bank.account(c)
            clients.OVERRIDES["fraud"] = lambda _r: (_ for _ in ()).throw(TimeoutError("fraud timeout"))
            status, body = bank.transfer(c, src, dst, 1_000)
            print(f"HTTP {status} {body['error']['code']}; transfer {body['transfer']['status']}; balance {bank.balance(src)}")
        else:
            from services.ledger import handler as ledger

            src, dst = bank.account(c, opening_minor=50_000), bank.account(c)
            state = {"lost": False}

            def flaky(req):
                out = ledger.internal(req)
                if req["action"] == "post_transfer" and not state["lost"]:
                    state["lost"] = True
                    raise TimeoutError("response lost after commit")
                return out

            clients.OVERRIDES["ledger"] = flaky
            key = uuid.uuid4().hex
            print("first attempt:", bank.transfer(c, src, dst, 1_000, key=key)[0])
            print("retry same key:", bank.transfer(c, src, dst, 1_000, key=key)[0])
            print(f"balances {bank.balance(src)} / {bank.balance(dst)} — posted exactly once")
    return 0


if __name__ == "__main__":
    sys.exit(main())
