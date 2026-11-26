#!/usr/bin/env python3
"""Run ledger reconciliation against the configured DynamoDB endpoint.

Locally: AWS_ENDPOINT_URL=http://127.0.0.1:5001 (started by local_api.py).
In AWS prefer the reconciliation workflow, which invokes the Lambda with its
least-privilege role.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workers.ledger_reconciliation.handler import run

if __name__ == "__main__":
    report = run(trigger="script")
    print(json.dumps({k: v for k, v in report.items() if k != "discrepancies"}, indent=2))
    for d in report["discrepancies"]:
        print("DISCREPANCY", json.dumps(d))
    sys.exit(0 if report["status"] == "BALANCED" else 1)
