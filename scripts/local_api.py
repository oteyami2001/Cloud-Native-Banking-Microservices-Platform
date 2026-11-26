#!/usr/bin/env python3
"""Offline NovaBank API for local development and demos (no AWS account).

* Starts an in-process moto server (or uses DynamoDB Local via
  AWS_ENDPOINT_URL), creates the tables, and serves the real Lambda handlers
  over HTTP on http://localhost:8080 with API Gateway v2-shaped events.
* Authentication is SIMULATED: ``Authorization: Bearer local:<subject>:<groups>``
  is turned into JWT claims. This shortcut is refused unless ENVIRONMENT=local
  and the server binds to 127.0.0.1 — it can never run in AWS.

Usage: python scripts/local_api.py [--port 8080]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("ENVIRONMENT", "local")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-2")
os.environ.setdefault("AWS_REGION", "us-east-2")
os.environ.setdefault("EVIDENCE_BUCKET", "novabank-local-evidence")
os.environ.setdefault("EVENT_BUS_NAME", "novabank-local-events")
for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
    os.environ[var] = "local"
os.environ.pop("AWS_SESSION_TOKEN", None)

if os.environ["ENVIRONMENT"] != "local":
    sys.exit("local_api.py only runs with ENVIRONMENT=local")


def _start_backend() -> None:
    if not os.environ.get("AWS_ENDPOINT_URL"):
        from moto.server import ThreadedMotoServer

        server = ThreadedMotoServer(ip_address="127.0.0.1", port=5001)
        server.start()
        os.environ["AWS_ENDPOINT_URL"] = "http://127.0.0.1:5001"
    import boto3

    from shared.schema import create_all

    ddb = boto3.client("dynamodb")
    if not ddb.list_tables()["TableNames"]:
        create_all(ddb)
        boto3.client("s3").create_bucket(
            Bucket=os.environ["EVIDENCE_BUCKET"], CreateBucketConfiguration={"LocationConstraint": "us-east-2"}
        )
        boto3.client("events").create_event_bus(Name=os.environ["EVENT_BUS_NAME"])
    from services.ledger.engine import Ledger
    from shared.config import GL_SYNTHETIC_FUNDING_ACCOUNT

    Ledger().open_account(GL_SYNTHETIC_FUNDING_ACCOUNT, customer_id=None, currency="USD", account_class="ASSET")


ROUTES: list[tuple[str, re.Pattern[str], str, object]] = []


def _register() -> None:
    from services.account.handler import handler as account
    from services.audit.handler import handler as audit
    from services.customer.handler import handler as customer
    from services.fraud.handler import handler as fraud
    from services.notification.handler import handler as notification
    from services.transfer.handler import handler as transfer

    table = {
        "POST /v1/customers": customer,
        "GET /v1/customers/me": customer,
        "PATCH /v1/customers/me": customer,
        "POST /v1/accounts": account,
        "GET /v1/accounts": account,
        "GET /v1/accounts/{id}": account,
        "GET /v1/accounts/{id}/balance": account,
        "GET /v1/accounts/{id}/transactions": account,
        "POST /v1/transfers": transfer,
        "GET /v1/transfers/{id}": transfer,
        "POST /v1/admin/transfers/{id}/approve": transfer,
        "POST /v1/admin/transfers/{id}/reject": transfer,
        "GET /v1/admin/fraud-alerts": fraud,
        "GET /v1/admin/reconciliation": audit,
        "GET /v1/admin/audit/transfers/{id}": audit,
        "GET /v1/notifications": notification,
    }
    for key, fn in table.items():
        method, path = key.split(" ", 1)
        ROUTES.append((method, re.compile("^" + path.replace("{id}", "(?P<id>[A-Z0-9-]+)") + "$"), key, fn))


def _claims(auth: str | None) -> dict | None:
    if not auth or not auth.startswith("Bearer local:"):
        return None
    _, subject, groups = (auth.removeprefix("Bearer ") + "::").split(":")[:3]
    admin = "fraud-reviewers" in groups or "auditors" in groups
    return {
        "sub": subject,
        "username": subject,
        "token_use": "access",
        "exp": str(int(time.time()) + 3600),
        "scope": "novabank/read novabank/write" + (" novabank/admin" if admin else ""),
        "cognito:groups": "[" + groups.replace(",", " ") + "]",
    }


def _drain_outbox() -> None:
    """Locally deliver outbox events to the notification and audit consumers."""

    from services.audit.handler import record_event
    from services.notification.handler import handle_event
    from shared import aws
    from shared.config import tables
    from workers.outbox_publisher.handler import mark_published

    table = aws.table(tables().outbox)
    for item in table.query(
        IndexName="PendingIndex", KeyConditionExpression="pending_partition = :p", ExpressionAttributeValues={":p": "PENDING"}
    ).get("Items", []):
        full = table.get_item(Key={"PK": item["PK"], "SK": "METADATA"})["Item"]
        event = json.loads(full["payload"])
        handle_event(event)
        record_event(event)
        mark_published(item["PK"])


class Handler(BaseHTTPRequestHandler):
    def _cors(self) -> None:
        self.send_header("access-control-allow-origin", "http://localhost:5173")
        self.send_header("access-control-allow-headers", "authorization, content-type, idempotency-key, x-correlation-id")
        self.send_header("access-control-allow-methods", "GET, POST, PATCH, OPTIONS")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _dispatch(self) -> None:
        path, _, qs = self.path.partition("?")
        for method, pattern, key, fn in ROUTES:
            m = pattern.match(path)
            if method == self.command and m:
                length = int(self.headers.get("content-length") or 0)
                event = {
                    "version": "2.0",
                    "routeKey": key,
                    "headers": {k.lower(): v for k, v in self.headers.items() if k.lower() != "authorization"},
                    "pathParameters": m.groupdict() or None,
                    "queryStringParameters": dict(p.split("=", 1) for p in qs.split("&") if "=" in p) or None,
                    "requestContext": {"requestId": f"local-{uuid.uuid4().hex[:12]}"},
                    "body": self.rfile.read(length).decode() if length else None,
                }
                claims = _claims(self.headers.get("authorization"))
                if claims:
                    event["requestContext"]["authorizer"] = {"jwt": {"claims": claims}}
                resp = fn(event)
                _drain_outbox()
                self.send_response(resp["statusCode"])
                for k, v in resp["headers"].items():
                    self.send_header(k, v)
                self._cors()
                self.end_headers()
                self.wfile.write(resp["body"].encode())
                return
        self.send_response(404)
        self._cors()
        self.end_headers()

    do_GET = do_POST = do_PATCH = _dispatch


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    _start_backend()
    _register()
    print(f"NovaBank local API (synthetic sandbox) on http://127.0.0.1:{args.port}")
    print("Auth: 'Authorization: Bearer local:<subject>:<groups>' — local simulation only")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
