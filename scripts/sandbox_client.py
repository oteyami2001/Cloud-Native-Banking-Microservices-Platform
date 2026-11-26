"""Small HTTP client for the NovaBank API used by the simulation scripts.

Targets the offline API (scripts/local_api.py) by default. Against AWS, pass
--api and an access token from the Cognito hosted UI via NOVABANK_TOKEN; tokens
are never printed or written to disk.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from typing import Any


class Api:
    def __init__(self, base: str, subject: str | None = None, groups: str = "customers"):
        self.base = base.rstrip("/")
        token = os.environ.get("NOVABANK_TOKEN")
        self.auth = f"Bearer {token}" if token else f"Bearer local:{subject or uuid.uuid4()}:{groups}"

    def call(self, method: str, path: str, body: Any = None, *, idempotency_key: str | None = None) -> tuple[int, Any]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("authorization", self.auth)
        req.add_header("content-type", "application/json")
        if idempotency_key:
            req.add_header("idempotency-key", idempotency_key)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status, json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read() or b"null")
