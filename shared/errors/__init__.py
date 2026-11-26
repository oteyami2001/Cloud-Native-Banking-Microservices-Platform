"""Standardized domain and API errors.

Every error carries a stable machine-readable ``code`` and an HTTP status. The
API layer renders them as::

    {"error": {"code": "...", "message": "...", "correlation_id": "..."}}

Messages must never contain secrets, tokens or sensitive customer data.
"""

from __future__ import annotations

from typing import Any


class BankingError(Exception):
    """Base class for all expected, client-visible errors."""

    status: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str | None = None, *, details: dict[str, Any] | None = None):
        super().__init__(message or self.code)
        self.message = message or self.code.replace("_", " ").capitalize()
        self.details = details or {}

    def to_body(self, correlation_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            body["details"] = self.details
        if correlation_id:
            body["correlation_id"] = correlation_id
        return {"error": body}


class ValidationError(BankingError):
    status, code = 400, "VALIDATION_ERROR"


class AuthenticationError(BankingError):
    status, code = 401, "UNAUTHENTICATED"


class ForbiddenError(BankingError):
    status, code = 403, "FORBIDDEN"


class NotFoundError(BankingError):
    """Also used for objects owned by other customers (avoids ID enumeration)."""

    status, code = 404, "NOT_FOUND"


class ConflictError(BankingError):
    status, code = 409, "CONFLICT"


class IdempotencyKeyReusedError(BankingError):
    status, code = 422, "IDEMPOTENCY_KEY_REUSED"


class RequestInProgressError(BankingError):
    status, code = 409, "REQUEST_IN_PROGRESS"


class InsufficientFundsError(BankingError):
    status, code = 422, "INSUFFICIENT_FUNDS"


class AccountNotActiveError(BankingError):
    status, code = 422, "ACCOUNT_NOT_ACTIVE"


class CurrencyMismatchError(BankingError):
    status, code = 422, "CURRENCY_MISMATCH"


class InvalidStateError(BankingError):
    status, code = 409, "INVALID_STATE"


class DuplicatePostingError(BankingError):
    """Raised by the ledger when a journal has already been posted."""

    status, code = 409, "DUPLICATE_POSTING"


class ConcurrencyConflictError(BankingError):
    status, code = 409, "CONCURRENCY_CONFLICT"


class DependencyUnavailableError(BankingError):
    """A required downstream dependency (for example fraud screening) failed.

    Financial operations fail closed when this is raised.
    """

    status, code = 503, "DEPENDENCY_UNAVAILABLE"


class SeparationOfDutiesError(BankingError):
    status, code = 403, "SEPARATION_OF_DUTIES"


__all__ = [
    "AccountNotActiveError",
    "AuthenticationError",
    "BankingError",
    "ConcurrencyConflictError",
    "ConflictError",
    "CurrencyMismatchError",
    "DependencyUnavailableError",
    "DuplicatePostingError",
    "ForbiddenError",
    "IdempotencyKeyReusedError",
    "InsufficientFundsError",
    "InvalidStateError",
    "NotFoundError",
    "RequestInProgressError",
    "SeparationOfDutiesError",
    "ValidationError",
]
