"""Minimal router for API Gateway HTTP API (payload format 2.0) events."""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from shared.auth import Principal, principal_from_event
from shared.errors import BankingError, ValidationError
from shared.logging import get_logger, log, set_correlation_id

MAX_BODY_BYTES = 16 * 1024
_CORRELATION_RE = re.compile(r"^[A-Za-z0-9\-_.]{8,128}$")

SECURITY_HEADERS = {
    "content-type": "application/json",
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
    "strict-transport-security": "max-age=63072000; includeSubDomains",
}


@dataclass
class Request:
    method: str
    route_key: str
    path_params: dict[str, str]
    query: dict[str, str]
    headers: dict[str, str]
    body: Any
    principal: Principal
    correlation_id: str
    raw: dict[str, Any] = field(repr=False, default_factory=dict)


Handler = Callable[[Request], tuple[int, Any]]


def _parse_body(event: dict[str, Any]) -> Any:
    raw = event.get("body")
    if raw in (None, ""):
        return None
    if event.get("isBase64Encoded"):
        try:
            raw = base64.b64decode(raw).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as exc:
            raise ValidationError("Body is not valid base64 UTF-8") from exc
    if len(raw.encode("utf-8")) > MAX_BODY_BYTES:
        raise ValidationError("Request body is too large")
    try:
        # parse_float rejects floats outright: money must be integer minor units.
        return json.loads(raw, parse_float=_reject_float)
    except json.JSONDecodeError as exc:
        raise ValidationError("Body is not valid JSON") from exc


def _reject_float(_: str) -> Any:
    raise ValidationError("Floating-point numbers are not accepted; use integer minor units")


def response(status: int, body: Any, correlation_id: str | None) -> dict[str, Any]:
    headers = dict(SECURITY_HEADERS)
    if correlation_id:
        headers["x-correlation-id"] = correlation_id
    return {
        "statusCode": status,
        "headers": headers,
        "body": json.dumps(body, separators=(",", ":")) if body is not None else "",
    }


class Router:
    def __init__(self, service: str):
        self.service = service
        self.routes: dict[str, Handler] = {}
        self.logger = get_logger(service)

    def route(self, route_key: str) -> Callable[[Handler], Handler]:
        def register(fn: Handler) -> Handler:
            self.routes[route_key] = fn
            return fn

        return register

    def __call__(self, event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
        headers = {str(k).lower(): str(v) for k, v in (event.get("headers") or {}).items()}
        supplied = headers.get("x-correlation-id", "")
        correlation_id = (
            supplied
            if _CORRELATION_RE.match(supplied)
            else event.get("requestContext", {}).get("requestId", "local-request")
        )
        set_correlation_id(correlation_id)
        route_key = event.get("routeKey", "")
        try:
            handler = self.routes.get(route_key)
            if handler is None:
                return response(404, {"error": {"code": "ROUTE_NOT_FOUND", "message": "Not found"}}, correlation_id)
            principal = principal_from_event(event)
            request = Request(
                method=route_key.split(" ", 1)[0],
                route_key=route_key,
                path_params=event.get("pathParameters") or {},
                query=event.get("queryStringParameters") or {},
                headers=headers,
                body=_parse_body(event),
                principal=principal,
                correlation_id=correlation_id,
                raw=event,
            )
            status, body = handler(request)
            log(self.logger, logging.INFO, "request.completed", route=route_key, status=status)
            return response(status, body, correlation_id)
        except BankingError as err:
            log(self.logger, logging.WARNING, "request.rejected", route=route_key, status=err.status, code=err.code)
            return response(err.status, err.to_body(correlation_id), correlation_id)
        except Exception:  # noqa: BLE001 - convert unexpected failures into a safe 500
            self.logger.exception("request.failed", extra={"fields": {"route": route_key}})
            body = {"error": {"code": "INTERNAL_ERROR", "message": "Internal error", "correlation_id": correlation_id}}
            return response(500, body, correlation_id)


def encode_cursor(key: dict[str, Any] | None) -> str | None:
    if not key:
        return None
    return base64.urlsafe_b64encode(json.dumps(key, sort_keys=True).encode()).decode()


def decode_cursor(cursor: str | None, *, expected: dict[str, str]) -> dict[str, Any] | None:
    """Decode a pagination cursor and verify it stays inside the caller's partition.

    Without this check a tampered cursor could be used to page through another
    customer's data (OWASP API1: broken object level authorization).
    """

    if not cursor:
        return None
    try:
        key = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise ValidationError("Invalid pagination cursor") from exc
    if not isinstance(key, dict) or any(key.get(k) != v for k, v in expected.items()):
        raise ValidationError("Invalid pagination cursor")
    return key


def page_limit(query: dict[str, str], default: int = 25, maximum: int = 100) -> int:
    raw = query.get("limit")
    if raw is None:
        return default
    if not raw.isdigit() or not 1 <= int(raw) <= maximum:
        raise ValidationError(f"limit must be an integer between 1 and {maximum}")
    return int(raw)
