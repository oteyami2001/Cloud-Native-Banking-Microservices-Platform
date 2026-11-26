"""Identifier and timestamp helpers.

IDs are time-ordered (millisecond timestamp prefix + random suffix) so that
sort keys built from them are naturally chronological, similar to ULIDs, while
remaining dependency free.
"""

from __future__ import annotations

import re
import secrets
import time
from datetime import UTC, datetime

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32
ID_RE = re.compile(r"^[A-Z]{2,4}-[0-9A-Z]{20}$")


def _b32(value: int, length: int) -> str:
    out = []
    for _ in range(length):
        value, rem = divmod(value, 32)
        out.append(_ALPHABET[rem])
    return "".join(reversed(out))


def new_id(prefix: str) -> str:
    millis = int(time.time() * 1000)
    return f"{prefix}-{_b32(millis, 10)}{_b32(secrets.randbits(50), 10)}"


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def now_epoch() -> int:
    return int(time.time())


def parse_iso(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
