"""Integer minor-unit money handling.

All monetary values are stored and calculated as ``int`` minor units (cents for
USD). Binary floating point is rejected at every boundary. Decimal strings such
as ``"250.00"`` are accepted from humans and converted exactly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from shared.errors import ValidationError

#: Supported ISO 4217 currencies and their minor-unit exponent.
SUPPORTED_CURRENCIES: dict[str, int] = {"USD": 2}

#: Upper bound for a single synthetic transfer (USD 1,000,000.00).
MAX_TRANSFER_MINOR = 100_000_000
#: Upper bound for any single balance (USD 10,000,000,000.00) to stay far away
#: from DynamoDB's 38-digit number precision.
MAX_BALANCE_MINOR = 1_000_000_000_000

_DECIMAL_RE = re.compile(r"^(0|[1-9]\d{0,11})(\.\d{1,2})?$")


def validate_currency(currency: object) -> str:
    if not isinstance(currency, str) or currency not in SUPPORTED_CURRENCIES:
        raise ValidationError("Unsupported currency", details={"supported": sorted(SUPPORTED_CURRENCIES)})
    return currency


def validate_amount_minor(amount: object, *, maximum: int = MAX_TRANSFER_MINOR) -> int:
    """Validate a positive integer amount in minor units.

    ``bool`` is rejected explicitly because ``True`` is an ``int`` in Python.
    Floats are always rejected, even when integral, to keep the API contract
    unambiguous.
    """

    if isinstance(amount, bool) or not isinstance(amount, int):
        raise ValidationError("amount_minor must be an integer number of minor units")
    if amount <= 0:
        raise ValidationError("amount_minor must be greater than zero")
    if amount > maximum:
        raise ValidationError("amount_minor exceeds the permitted maximum", details={"maximum": maximum})
    return amount


def parse_decimal_amount(value: str, currency: str = "USD") -> int:
    """Convert a human decimal string (``"250.00"``) to minor units exactly."""

    validate_currency(currency)
    if not isinstance(value, str) or not _DECIMAL_RE.match(value.strip()):
        raise ValidationError("Amount must be a decimal string with at most two fractional digits")
    try:
        quantized = Decimal(value.strip()) * (10 ** SUPPORTED_CURRENCIES[currency])
    except InvalidOperation as exc:  # pragma: no cover - regex guards this
        raise ValidationError("Malformed amount") from exc
    return validate_amount_minor(int(quantized))


def format_minor(amount_minor: int, currency: str = "USD") -> str:
    exponent = SUPPORTED_CURRENCIES[validate_currency(currency)]
    sign = "-" if amount_minor < 0 else ""
    whole, frac = divmod(abs(amount_minor), 10**exponent)
    return f"{sign}{whole}.{frac:0{exponent}d}"


@dataclass(frozen=True, slots=True)
class Money:
    amount_minor: int
    currency: str

    def __post_init__(self) -> None:
        if isinstance(self.amount_minor, bool) or not isinstance(self.amount_minor, int):
            raise ValidationError("Money requires integer minor units")
        validate_currency(self.currency)

    def __add__(self, other: Money) -> Money:
        self._same_currency(other)
        return Money(self.amount_minor + other.amount_minor, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._same_currency(other)
        return Money(self.amount_minor - other.amount_minor, self.currency)

    def _same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValidationError("Currency mismatch")

    def __str__(self) -> str:
        return f"{format_minor(self.amount_minor, self.currency)} {self.currency}"
