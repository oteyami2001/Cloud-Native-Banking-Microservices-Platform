"""Transactional outbox, EventBridge publication and idempotent consumers."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import boto3
import pytest

from services.audit.handler import handler as audit_handler
from services.notification.handler import handler as notification_handler
from workers.outbox_publisher import handler as publisher
from workers.outbox_reconciliation.handler import run as reconcile_outbox


def stream_records(bank):
    """Build DynamoDB Streams INSERT records for every outbox item."""

    from boto3.dynamodb.types import TypeSerializer

    ser = TypeSerializer()
    records = []
    for n, item in enumerate(bank.scan("outbox")):
        records.append(
            {
                "eventName": "INSERT",
                "dynamodb": {"SequenceNumber": str(100 + n), "NewImage": {k: ser.serialize(v) for k, v in item.items()}},
            }
        )
    return records


def sqs_batch(events):
    return {
        "Records": [
            {"messageId": f"m-{i}", "body": json.dumps({"detail-type": e["event_type"], "detail": e})} for i, e in enumerate(events)
        ]
    }


def outbox_events(bank, event_type=None):
    events = [json.loads(i["payload"]) for i in bank.scan("outbox")]
    return [e for e in events if event_type is None or e["event_type"] == event_type]


def test_events_are_committed_with_the_transaction(bank):
    c = bank.customer()
    src, dst = bank.account(c, opening_minor=10_000), bank.account(c)
    bank.transfer(c, src, dst, 1_000)
    types = sorted(e["event_type"] for e in outbox_events(bank))
    assert types.count("TransferCompleted") == 1 and "TransferRequested" in types
    assert all(i["status"] == "PENDING" for i in bank.scan("outbox"))
    # A rejected transfer never produces TransferCompleted.
    bank.transfer(c, src, dst, 999_999)
    assert len(outbox_events(bank, "TransferCompleted")) == 1


def test_publisher_publishes_and_marks_items(bank):
    c = bank.customer()
    bank.account(c, opening_minor=10_000)
    result = publisher.handler({"Records": stream_records(bank)})
    assert result == {"batchItemFailures": []}
    items = bank.scan("outbox")
    assert all(i["status"] == "PUBLISHED" and "pending_partition" not in i for i in items)
    # MODIFY records (from marking) are ignored.
    assert publisher.handler({"Records": [{"eventName": "MODIFY", "dynamodb": {"SequenceNumber": "1"}}]}) == {"batchItemFailures": []}


@pytest.mark.scenario("T20")
def test_partial_publication_failure_is_reported_and_recoverable(bank, monkeypatch):
    c = bank.customer()
    bank.account(c, opening_minor=10_000)
    records = stream_records(bank)
    assert len(records) >= 3
    real = boto3.client("events", region_name="us-east-2")

    class Flaky:
        def put_events(self, Entries):
            result = real.put_events(Entries=Entries)
            result["Entries"][0] = {"ErrorCode": "InternalFailure", "ErrorMessage": "injected"}
            result["FailedEntryCount"] = 1
            return result

    monkeypatch.setattr(publisher.aws, "client", lambda name: Flaky() if name == "events" else real)
    result = publisher.handler({"Records": records})
    assert len(result["batchItemFailures"]) == 1
    pending = [i for i in bank.scan("outbox") if i["status"] == "PENDING"]
    assert len(pending) == 1
    monkeypatch.undo()

    # The scheduled outbox reconciliation republishes it after the grace period.
    later = datetime.now(UTC) + timedelta(minutes=5)
    report = reconcile_outbox(now=later)
    assert report["republished"] == 1 and report["failed"] == 0
    assert all(i["status"] == "PUBLISHED" for i in bank.scan("outbox"))


def test_permanently_failing_events_are_retained_not_deleted(bank, monkeypatch):
    c = bank.customer()
    bank.account(c)
    from workers.outbox_reconciliation import handler as recon

    monkeypatch.setattr(recon, "publish", lambda payloads: ([], [pk for pk, _ in payloads]))
    monkeypatch.setattr(recon, "MAX_ATTEMPTS", 2)
    later = datetime.now(UTC) + timedelta(minutes=5)
    recon.run(now=later)
    report = recon.run(now=later)
    assert report["dead_lettered"] >= 1
    statuses = {i["status"] for i in bank.scan("outbox")}
    assert "FAILED_PUBLISH" in statuses and len(bank.scan("outbox")) >= 2


@pytest.mark.scenario("T21")
def test_duplicate_event_delivery_is_handled_safely(bank):
    c = bank.customer()
    src, dst = bank.account(c, opening_minor=10_000), bank.account(c)
    bank.transfer(c, src, dst, 1_000)
    events = outbox_events(bank)
    batch = sqs_batch(events + events)  # every event delivered twice
    assert notification_handler(batch) == {"batchItemFailures": []}
    assert audit_handler(batch) == {"batchItemFailures": []}
    notes = bank.call("GET /v1/notifications", c["claims"])[1]["items"]
    assert len([n for n in notes if n["event_type"] == "TransferCompleted"]) == 1
    audit_items = bank.scan("audit")
    assert len(audit_items) == len(events)


@pytest.mark.scenario("T22")
def test_notification_failure_enters_retry_flow(bank, monkeypatch):
    c = bank.customer()
    bank.account(c)
    events = outbox_events(bank)
    monkeypatch.setenv("NOTIFICATION_FAULT_INJECTION", "fail")
    result = notification_handler(sqs_batch(events))
    # Every message is reported failed -> SQS redelivers, then the DLQ after maxReceiveCount.
    assert len(result["batchItemFailures"]) == len(events)
    monkeypatch.delenv("NOTIFICATION_FAULT_INJECTION")
    assert notification_handler(sqs_batch(events)) == {"batchItemFailures": []}


def test_poison_message_fails_individually(bank):
    batch = {"Records": [{"messageId": "bad", "body": "not json"}]}
    assert notification_handler(batch) == {"batchItemFailures": [{"itemIdentifier": "bad"}]}


@pytest.mark.scenario("T23")
def test_audit_evidence_is_generated_with_checksum(bank):
    import hashlib

    c = bank.customer()
    src, dst = bank.account(c, opening_minor=10_000), bank.account(c)
    tid = bank.transfer(c, src, dst, 1_000)[1]["transfer_id"]
    audit_handler(sqs_batch(outbox_events(bank)))
    auditor = {"sub": "aud-1", "scope": "novabank/admin", "cognito:groups": "[auditors]", "token_use": "access"}
    status, body = bank.call("GET /v1/admin/audit/transfers/{id}", auditor, path={"id": tid})
    assert status == 200
    trail = body["items"]
    assert [i["event_type"] for i in trail] == ["TransferRequested", "FraudScreeningCompleted", "TransferCompleted"]
    s3 = boto3.client("s3", region_name="us-east-2")
    for item in trail:
        obj = s3.get_object(Bucket="novabank-test-evidence", Key=item["s3_key"])["Body"].read()
        assert hashlib.sha256(obj).hexdigest() == item["sha256"]
        assert json.loads(obj)["correlation_id"]


def test_ops_alert_published_to_sns_without_customer_identifiers(bank, monkeypatch):
    sns = boto3.client("sns", region_name="us-east-2")
    topic = sns.create_topic(Name="ops")["TopicArn"]
    monkeypatch.setenv("OPS_TOPIC_ARN", topic)
    c = bank.customer()
    src, dst = bank.account(c, opening_minor=2_000_000), bank.account(c)
    bank.transfer(c, src, dst, 600_000)
    alerts = outbox_events(bank, "FraudAlertRaised")
    assert alerts
    sent = []
    real_client = notification_handler.__globals__["aws"].client

    class Spy:
        def publish(self, **kw):
            sent.append(kw)
            return {"MessageId": "1"}

    monkeypatch.setattr(notification_handler.__globals__["aws"], "client", lambda n: Spy() if n == "sns" else real_client(n))
    assert notification_handler(sqs_batch(alerts)) == {"batchItemFailures": []}
    assert sent and c["customer_id"] not in sent[0]["Message"]
