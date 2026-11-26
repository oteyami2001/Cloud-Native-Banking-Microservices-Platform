"""Structured JSON logging with correlation IDs and redaction.

Logs are emitted as single-line JSON documents for CloudWatch Logs Insights.
Known sensitive keys are redacted recursively; access tokens must never be
passed to the logger in the first place, the redaction is a safety net.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from contextvars import ContextVar
from typing import Any

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)

REDACTED = "[REDACTED]"
SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "access_token",
        "id_token",
        "refresh_token",
        "token",
        "password",
        "secret",
        "email",
        "phone_number",
        "cookie",
        "x-api-key",
    }
)


def set_correlation_id(value: str | None) -> None:
    _correlation_id.set(value)


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: (REDACTED if str(k).lower() in SENSITIVE_KEYS else redact(v)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        doc: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "service": os.environ.get("SERVICE_NAME", "novabank"),
            "message": record.getMessage(),
            "correlation_id": get_correlation_id(),
        }
        extra = getattr(record, "fields", None)
        if extra:
            doc.update(redact(extra))
        if record.exc_info:
            doc["exception"] = self.formatException(record.exc_info)
        return json.dumps(doc, default=str, separators=(",", ":"))


def get_logger(name: str = "novabank") -> logging.Logger:
    logger = logging.getLogger(name)
    if not getattr(logger, "_novabank_configured", False):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.handlers = [handler]
        logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
        logger.propagate = False
        logger._novabank_configured = True  # type: ignore[attr-defined]
    return logger


def log(logger: logging.Logger, level: int, message: str, **fields: Any) -> None:
    logger.log(level, message, extra={"fields": fields})
