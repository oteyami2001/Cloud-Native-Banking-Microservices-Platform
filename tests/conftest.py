"""Shared fixtures: every test runs against moto — no AWS credentials needed."""

from __future__ import annotations

import os

# Must be set before boto3 creates any client. Overrides any real or
# proxy-injected credentials so tests can never touch a live account.
os.environ.update(
    {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "us-east-2",
        "AWS_REGION": "us-east-2",
        "ENVIRONMENT": "local",
        "SANDBOX_OPENING_BALANCES_ENABLED": "true",
        "EVIDENCE_BUCKET": "novabank-test-evidence",
        "EVENT_BUS_NAME": "novabank-test-events",
    }
)
for var in ("AWS_PROFILE", "AWS_CA_BUNDLE", "LEDGER_FUNCTION_NAME", "FRAUD_FUNCTION_NAME", "ACCOUNT_FUNCTION_NAME"):
    os.environ.pop(var, None)

import boto3  # noqa: E402
import pytest  # noqa: E402
from moto import mock_aws  # noqa: E402

from shared import aws, clients  # noqa: E402
from shared.schema import create_all  # noqa: E402
from tests.support import Bank  # noqa: E402


def _serialise_moto_calls() -> None:
    """moto is not thread-safe; DynamoDB executes each API call atomically.

    Serialising each mocked API call reproduces DynamoDB's per-request
    atomicity while still letting concurrent requests interleave between
    calls, which is exactly the window the conditional writes must protect.
    """

    import threading

    from moto.core.botocore_stubber import BotocoreStubber

    if getattr(BotocoreStubber, "_novabank_locked", False):
        return
    lock = threading.RLock()
    original = BotocoreStubber.__call__

    def locked(self, *args, **kwargs):
        with lock:
            return original(self, *args, **kwargs)

    BotocoreStubber.__call__ = locked
    BotocoreStubber._novabank_locked = True


_serialise_moto_calls()


@pytest.fixture
def aws_env():
    with mock_aws():
        aws.reset_clients()
        create_all(boto3.client("dynamodb", region_name="us-east-2"))
        boto3.client("s3", region_name="us-east-2").create_bucket(
            Bucket="novabank-test-evidence", CreateBucketConfiguration={"LocationConstraint": "us-east-2"}
        )
        boto3.client("events", region_name="us-east-2").create_event_bus(Name="novabank-test-events")
        from services.fraud.rules import load_policy

        load_policy.cache_clear()
        clients.OVERRIDES.clear()
        yield
        clients.OVERRIDES.clear()
        aws.reset_clients()


@pytest.fixture
def bank(aws_env):
    return Bank()
