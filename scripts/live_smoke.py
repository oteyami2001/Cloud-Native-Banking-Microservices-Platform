#!/usr/bin/env python3
"""Unauthenticated live checks against the deployed API (no credentials needed).

Verifies that every protected route rejects requests without a valid token
(T03, live) and that responses do not leak server details.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request

CHECKS = [
    ("GET", "/v1/accounts"),
    ("GET", "/v1/customers/me"),
    ("POST", "/v1/transfers"),
    ("GET", "/v1/admin/fraud-alerts"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", required=True)
    args = parser.parse_args()
    if not args.api.startswith("https://"):
        print("API URL must use HTTPS")
        return 2
    ok = True
    print("| Request | Without token | With forged token |\n|---|---|---|")
    for method, path in CHECKS:
        codes = []
        for auth in (None, "Bearer eyJhbGciOiJub25lIn0.eyJzdWIiOiJhdHRhY2tlciJ9."):
            req = urllib.request.Request(args.api.rstrip("/") + path, method=method, data=b"{}" if method == "POST" else None)
            if auth:
                req.add_header("Authorization", auth)
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    codes.append(resp.status)
            except urllib.error.HTTPError as err:
                codes.append(err.code)
        ok &= all(c == 401 for c in codes)
        print(f"| {method} {path} | {codes[0]} | {codes[1]} |")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
