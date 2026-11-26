"""Strict request validation without third-party dependencies.

Unknown fields are rejected (OWASP API3: broken object property level
authorization / mass assignment), types are checked exactly and strings are
bounded.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

from shared.errors import ValidationError

Validator = Callable[[str, Any], Any]


def validate_object(
    body: Any,
    *,
    required: Mapping[str, Validator],
    optional: Mapping[str, Validator] | None = None,
) -> dict[str, Any]:
    optional = optional or {}
    if not isinstance(body, dict):
        raise ValidationError("Request body must be a JSON object")
    unknown = sorted(set(body) - set(required) - set(optional))
    if unknown:
        raise ValidationError("Unknown fields are not permitted", details={"fields": unknown})
    missing = sorted(k for k in required if k not in body)
    if missing:
        raise ValidationError("Required fields are missing", details={"fields": missing})
    out: dict[str, Any] = {}
    for name, check in {**required, **optional}.items():
        if name in body:
            out[name] = check(name, body[name])
    return out


def string(*, min_len: int = 1, max_len: int = 128, pattern: str | None = None, choices: set[str] | None = None) -> Validator:
    compiled = re.compile(pattern) if pattern else None

    def check(name: str, value: Any) -> str:
        if not isinstance(value, str):
            raise ValidationError(f"{name} must be a string")
        if not min_len <= len(value) <= max_len:
            raise ValidationError(f"{name} length must be between {min_len} and {max_len}")
        if compiled and not compiled.fullmatch(value):
            raise ValidationError(f"{name} has an invalid format")
        if choices is not None and value not in choices:
            raise ValidationError(f"{name} must be one of {sorted(choices)}")
        return value

    return check


def integer(*, minimum: int, maximum: int) -> Validator:
    def check(name: str, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValidationError(f"{name} must be an integer")
        if not minimum <= value <= maximum:
            raise ValidationError(f"{name} must be between {minimum} and {maximum}")
        return value

    return check


def boolean() -> Validator:
    def check(name: str, value: Any) -> bool:
        if not isinstance(value, bool):
            raise ValidationError(f"{name} must be a boolean")
        return value

    return check


ACCOUNT_ID_PATTERN = r"ACC-[0-9A-Z]{20}"
TRANSFER_ID_PATTERN = r"TRF-[0-9A-Z]{20}"
IDEMPOTENCY_KEY_PATTERN = r"[A-Za-z0-9_\-]{16,128}"


def path_id(value: Any, pattern: str, name: str = "id") -> str:
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ValidationError(f"Invalid {name}")
    return value


def internal_safe_string(max_len: int) -> Validator:
    """Free text limited to a conservative character set (no markup)."""

    return string(min_len=1, max_len=max_len, pattern=r"[\w .,'\-]+")
