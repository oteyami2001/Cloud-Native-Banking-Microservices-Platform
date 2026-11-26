"""Lazily created, cached AWS SDK clients.

``AWS_ENDPOINT_URL_DYNAMODB`` (natively supported by botocore) can point the
services at DynamoDB Local for offline development.
"""

from __future__ import annotations

import os
from decimal import Decimal
from functools import cache
from typing import Any

import boto3
from botocore.config import Config

_CONFIG = Config(
    retries={"mode": "standard", "max_attempts": 3},
    connect_timeout=2,
    read_timeout=5,
)


def _region() -> str:
    return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-2"


@cache
def dynamodb_resource() -> Any:
    return boto3.resource("dynamodb", region_name=_region(), config=_CONFIG)


def dynamodb_client() -> Any:
    """Client that accepts and returns native Python types.

    The resource's embedded client has boto3's type (de)serialization hooks
    registered, which is required for readable ``transact_write_items`` calls.
    """

    return dynamodb_resource().meta.client


def table(name: str) -> Any:
    return dynamodb_resource().Table(name)


@cache
def client(service: str) -> Any:
    return boto3.client(service, region_name=_region(), config=_CONFIG)


def reset_clients() -> None:
    """Drop cached clients (used by tests that start new moto mocks)."""

    dynamodb_resource.cache_clear()
    client.cache_clear()


def to_native(value: Any) -> Any:
    """Convert DynamoDB ``Decimal`` values back to ``int`` recursively.

    Monetary values are always integers, so a non-integral Decimal indicates
    corrupted data and is rejected rather than silently converted to float.
    """

    if isinstance(value, Decimal):
        if value != value.to_integral_value():
            raise ValueError("Non-integral numeric value found in banking data")
        return int(value)
    if isinstance(value, dict):
        return {k: to_native(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_native(v) for v in value]
    if isinstance(value, set):
        return {to_native(v) for v in value}
    return value
