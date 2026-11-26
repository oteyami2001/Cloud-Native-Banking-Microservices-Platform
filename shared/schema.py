"""Physical DynamoDB schema — single source of truth for local tables.

Terraform (terraform/modules/dynamodb) declares the same keys, indexes and
streams; tests/terraform/test_schema_parity.py keeps the two in sync.
"""

from __future__ import annotations

from typing import Any

from shared.config import tables

S = "S"


def _gsi(name: str, pk: str, sk: str) -> dict[str, Any]:
    return {
        "IndexName": name,
        "KeySchema": [{"AttributeName": pk, "KeyType": "HASH"}, {"AttributeName": sk, "KeyType": "RANGE"}],
        "Projection": {"ProjectionType": "ALL"},
    }


#: logical name -> (GSIs, stream enabled)
LOGICAL: dict[str, dict[str, Any]] = {
    "customers": {"gsis": [], "stream": False},
    "accounts": {"gsis": [("GSI1", "GSI1PK", "GSI1SK")], "stream": False},
    "ledger": {"gsis": [], "stream": False},
    "transfers": {"gsis": [("GSI1", "GSI1PK", "GSI1SK")], "stream": False},
    "idempotency": {"gsis": [], "stream": False},
    "fraud": {"gsis": [("GSI1", "GSI1PK", "GSI1SK")], "stream": False},
    "outbox": {"gsis": [("PendingIndex", "pending_partition", "pending_since")], "stream": True},
    "notifications": {"gsis": [("GSI1", "GSI1PK", "GSI1SK")], "stream": False},
    "audit": {"gsis": [], "stream": False},
}


def create_table_kwargs() -> list[dict[str, Any]]:
    names = tables()
    out = []
    for logical, spec in LOGICAL.items():
        attrs = {"PK", "SK"}
        for _, pk, sk in spec["gsis"]:
            attrs.update({pk, sk})
        kwargs: dict[str, Any] = {
            "TableName": getattr(names, logical),
            "BillingMode": "PAY_PER_REQUEST",
            "KeySchema": [{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
            "AttributeDefinitions": [{"AttributeName": a, "AttributeType": S} for a in sorted(attrs)],
        }
        if spec["gsis"]:
            kwargs["GlobalSecondaryIndexes"] = [_gsi(*g) for g in spec["gsis"]]
        if spec["stream"]:
            kwargs["StreamSpecification"] = {"StreamEnabled": True, "StreamViewType": "NEW_IMAGE"}
        out.append(kwargs)
    return out


def create_all(client: Any) -> None:
    for kwargs in create_table_kwargs():
        client.create_table(**kwargs)
