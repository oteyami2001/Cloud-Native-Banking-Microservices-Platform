"""Runtime configuration resolved from environment variables.

Defaults match the logical table names in docs/database-design.md and are used
for local development and tests. Terraform injects environment-prefixed names
(for example ``novabank-dev-ledger``) in AWS.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Tables:
    customers: str
    accounts: str
    ledger: str
    transfers: str
    idempotency: str
    fraud: str
    outbox: str
    notifications: str
    audit: str


def tables() -> Tables:
    return Tables(
        customers=_env("CUSTOMERS_TABLE", "banking-customers"),
        accounts=_env("ACCOUNTS_TABLE", "banking-accounts"),
        ledger=_env("LEDGER_TABLE", "banking-ledger"),
        transfers=_env("TRANSFERS_TABLE", "banking-transactions"),
        idempotency=_env("IDEMPOTENCY_TABLE", "banking-idempotency"),
        fraud=_env("FRAUD_TABLE", "banking-fraud"),
        outbox=_env("OUTBOX_TABLE", "banking-outbox"),
        notifications=_env("NOTIFICATIONS_TABLE", "banking-notifications"),
        audit=_env("AUDIT_TABLE", "banking-audit"),
    )


def event_bus_name() -> str:
    return _env("EVENT_BUS_NAME", "novabank-events")


def evidence_bucket() -> str:
    return _env("EVIDENCE_BUCKET", "novabank-local-evidence")


def deployment_version() -> str:
    return _env("DEPLOYMENT_VERSION", "local")


def sandbox_opening_balances_enabled() -> bool:
    return _env("SANDBOX_OPENING_BALANCES_ENABLED", "true").lower() == "true"


#: Synthetic general-ledger funding account used for documented opening balances.
GL_SYNTHETIC_FUNDING_ACCOUNT = "GL-1000"
