"""Audit & reporting service.

* Consumes every committed banking event from SQS and records evidence:
  a deterministic JSON document in the versioned, encrypted evidence bucket
  plus an index item (with SHA-256 checksum) in the audit table.
* Idempotent: the S3 object content is deterministic and the index item is
  written with a conditional put.
* The service role may write evidence; the application services may not.

Routes (auditors or fraud-reviewers with novabank/admin):
    GET /v1/admin/reconciliation              latest reconciliation reports
    GET /v1/admin/audit/transfers/{id}        evidence trail for one transfer
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from shared import aws, metrics
from shared.auth import GROUP_AUDITORS, GROUP_FRAUD_REVIEWERS, SCOPE_ADMIN
from shared.config import deployment_version, evidence_bucket, tables
from shared.http import Request, Router, page_limit
from shared.ids import now_iso
from shared.sqs import process_batch
from shared.validation import TRANSFER_ID_PATTERN, path_id

router = Router("audit")


def canonical(doc: dict[str, Any]) -> bytes:
    return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()


def write_evidence(key: str, doc: dict[str, Any]) -> str:
    body = canonical(doc)
    digest = hashlib.sha256(body).hexdigest()
    aws.client("s3").put_object(
        Bucket=evidence_bucket(),
        Key=key,
        Body=body,
        ContentType="application/json",
        ServerSideEncryption="aws:kms",
        Metadata={"sha256": digest},
    )
    return digest


def record_event(event: dict[str, Any]) -> None:
    day = event["occurred_at"][:10].replace("-", "/")
    s3_key = f"evidence/events/{day}/{event['event_type']}/{event['event_id']}.json"
    digest = write_evidence(s3_key, event)
    try:
        aws.table(tables().audit).put_item(
            Item={
                "PK": f"ENTITY#{event.get('entity_id', 'unknown')}",
                "SK": f"EVENT#{event['occurred_at']}#{event['event_id']}",
                "event_id": event["event_id"],
                "event_type": event["event_type"],
                "correlation_id": event.get("correlation_id"),
                "producer": event.get("producer"),
                "s3_key": s3_key,
                "sha256": digest,
                "event_deployment_version": event.get("deployment_version"),
                "recorder_deployment_version": deployment_version(),
                "recorded_at": now_iso(),
            },
            ConditionExpression="attribute_not_exists(PK)",
        )
        metrics.emit("AuditEvidenceRecorded")
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        metrics.emit("DuplicateEventIgnored")


def _require_admin(req: Request) -> None:
    req.principal.require_scope(SCOPE_ADMIN)
    req.principal.require_group(GROUP_AUDITORS, GROUP_FRAUD_REVIEWERS)


@router.route("GET /v1/admin/reconciliation")
def reconciliation(req: Request) -> tuple[int, Any]:
    _require_admin(req)
    result = aws.table(tables().audit).query(
        KeyConditionExpression=Key("PK").eq("REPORT#RECONCILIATION"),
        ScanIndexForward=False,
        Limit=page_limit(req.query, default=10, maximum=50),
    )
    items = [{k: v for k, v in aws.to_native(i).items() if k not in {"PK", "SK"}} for i in result.get("Items", [])]
    return 200, {"items": items}


@router.route("GET /v1/admin/audit/transfers/{id}")
def transfer_trail(req: Request) -> tuple[int, Any]:
    _require_admin(req)
    transfer_id = path_id(req.path_params.get("id"), TRANSFER_ID_PATTERN, "transfer id")
    result = aws.table(tables().audit).query(KeyConditionExpression=Key("PK").eq(f"ENTITY#{transfer_id}"), ScanIndexForward=True)
    items = [{k: v for k, v in aws.to_native(i).items() if k not in {"PK", "SK"}} for i in result.get("Items", [])]
    return 200, {"items": items}


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    if "routeKey" in event:
        return router(event, context)
    return process_batch(event, record_event, "audit")
