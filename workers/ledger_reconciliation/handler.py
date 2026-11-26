"""Scheduled ledger reconciliation job.

Reads the ledger and transfer tables with paginated scans (acceptable for a
batch job on a synthetic dataset; normal request paths never scan), runs the
pure checks in ``reconcile.py``, stores the report as audit evidence and emits
the ``ReconciliationDiscrepancies`` metric that drives a CloudWatch alarm.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from services.audit.handler import write_evidence
from shared import aws, metrics
from shared.config import deployment_version, tables
from shared.contracts import build_event, outbox_item
from shared.ids import new_id, now_iso
from workers.ledger_reconciliation.reconcile import reconcile


def _scan(table_name: str) -> list[dict[str, Any]]:
    table = aws.table(table_name)
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {"ConsistentRead": True}
    while True:
        page = table.scan(**kwargs)
        items.extend(aws.to_native(page.get("Items", [])))
        if "LastEvaluatedKey" not in page:
            return items
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def run(now: datetime | None = None, *, trigger: str = "schedule") -> dict[str, Any]:
    now = now or datetime.now(UTC)
    t = tables()
    report = reconcile(_scan(t.ledger), [i for i in _scan(t.transfers) if i.get("SK") == "METADATA"], now)
    run_id = new_id("REC")
    generated_at = now_iso()
    report.update({"run_id": run_id, "generated_at": generated_at, "trigger": trigger, "deployment_version": deployment_version()})
    s3_key = f"evidence/reconciliation/{generated_at[:10].replace('-', '/')}/{run_id}.json"
    digest = write_evidence(s3_key, report)
    event = build_event(
        "ReconciliationCompleted",
        {k: report[k] for k in ("run_id", "status", "discrepancy_count", "accounts_checked", "journals_checked")},
        correlation_id=run_id,
        producer="ledger-reconciliation",
        entity_id=run_id,
    )
    aws.dynamodb_client().transact_write_items(
        TransactItems=[
            {
                "Put": {
                    "TableName": t.audit,
                    "Item": {
                        "PK": "REPORT#RECONCILIATION",
                        "SK": f"RUN#{generated_at}#{run_id}",
                        **{
                            k: report[k]
                            for k in (
                                "run_id",
                                "status",
                                "accounts_checked",
                                "journals_checked",
                                "transfers_checked",
                                "total_assets_minor",
                                "total_liabilities_minor",
                                "discrepancy_count",
                                "generated_at",
                                "trigger",
                            )
                        },
                        "s3_key": s3_key,
                        "sha256": digest,
                    },
                }
            },
            {"Put": {"TableName": t.outbox, "Item": outbox_item(event)}},
        ]
    )
    metrics.emit("ReconciliationDiscrepancies", report["discrepancy_count"])
    return {**report, "s3_key": s3_key, "sha256": digest}


def handler(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    return run(trigger=(event or {}).get("trigger", "schedule"))
