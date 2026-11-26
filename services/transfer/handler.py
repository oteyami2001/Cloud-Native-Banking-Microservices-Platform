"""Payment & transfer service: request validation and transfer orchestration.

Routes:
    POST /v1/transfers                        request an internal transfer
    GET  /v1/transfers/{id}                   transfer status (owner or reviewer)
    POST /v1/admin/transfers/{id}/approve     approve a held transfer (reviewer)
    POST /v1/admin/transfers/{id}/reject      reject a held transfer (reviewer)

State machine (docs/microservices-design.md#transfer-state-machine)::

    SCREENING -> APPROVED_FOR_POSTING -> COMPLETED      (ledger, atomic)
              -> PENDING_REVIEW -> APPROVED_FOR_POSTING (reviewer, revalidated)
                                -> REJECTED             (reviewer)
              -> REJECTED                               (fraud policy)
              -> FAILED                                 (fraud unavailable: fail closed)
    APPROVED_FOR_POSTING -> REJECTED                    (ledger rejected: funds/status)

Only the ledger moves a transfer to COMPLETED, inside the same atomic
transaction that changes balances.
"""

from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError

from shared import aws, clients, metrics
from shared.auth import GROUP_FRAUD_REVIEWERS, SCOPE_ADMIN, SCOPE_READ, SCOPE_WRITE, Principal
from shared.config import tables
from shared.contracts import build_event, outbox_item
from shared.errors import (
    AccountNotActiveError,
    BankingError,
    ConcurrencyConflictError,
    CurrencyMismatchError,
    DependencyUnavailableError,
    ForbiddenError,
    InsufficientFundsError,
    InvalidStateError,
    NotFoundError,
    RequestInProgressError,
    SeparationOfDutiesError,
    ValidationError,
)
from shared.http import Request, Router
from shared.idempotency import IdempotencyStore, request_hash, validate_key
from shared.identity import customer_id_for
from shared.ids import new_id, now_iso, parse_iso
from shared.money import validate_amount_minor, validate_currency
from shared.validation import ACCOUNT_ID_PATTERN, TRANSFER_ID_PATTERN, internal_safe_string, path_id, string, validate_object

router = Router("transfer")

TERMINAL = {"COMPLETED", "REJECTED", "FAILED"}
#: Ledger errors that are definitive: nothing was posted and nothing will be.
DEFINITIVE_LEDGER_ERRORS = (InsufficientFundsError, AccountNotActiveError, CurrencyMismatchError, NotFoundError)


def _amount(_: str, value: Any) -> int:
    return validate_amount_minor(value)


def _currency(_: str, value: Any) -> str:
    return validate_currency(value)


def _table() -> Any:
    return aws.table(tables().transfers)


def _key(transfer_id: str) -> dict[str, str]:
    return {"PK": f"TRANSFER#{transfer_id}", "SK": "METADATA"}


def load_transfer(transfer_id: str) -> dict[str, Any] | None:
    item = _table().get_item(Key=_key(transfer_id), ConsistentRead=True).get("Item")
    return aws.to_native(item) if item else None


def fingerprint(t: dict[str, Any]) -> str:
    """Integrity hash over the immutable financial fields of a transfer."""

    return request_hash(
        {
            "transfer_id": t["transfer_id"],
            "customer_id": t["customer_id"],
            "source_account_id": t["source_account_id"],
            "destination_account_id": t["destination_account_id"],
            "amount_minor": t["amount_minor"],
            "currency": t["currency"],
        }
    )


def public_view(t: dict[str, Any], *, reviewer: bool = False) -> dict[str, Any]:
    view = {
        "transfer_id": t["transfer_id"],
        "status": t["status"],
        "source_account_id": t["source_account_id"],
        "destination_account_id": t["destination_account_id"],
        "amount_minor": t["amount_minor"],
        "currency": t["currency"],
        "memo": t.get("memo"),
        "reason_code": t.get("reason_code"),
        "created_at": t["created_at"],
        "updated_at": t.get("updated_at"),
        "posted_at": t.get("posted_at"),
        "synthetic": True,
    }
    if reviewer:
        view["fraud"] = {k: t.get(k) for k in ("fraud_decision", "risk_score", "triggered_rules", "policy_version", "fraud_decision_id")}
        view["reviewed_by"] = t.get("reviewed_by")
    return view


def _transition(
    transfer_id: str, expected: str, new: str, *, extra: dict[str, Any] | None = None, event: dict[str, Any] | None = None
) -> None:
    extra = {**(extra or {}), "updated_at": now_iso()}
    names = {"#s": "status", **{f"#f{i}": k for i, k in enumerate(extra)}}
    values = {":new": new, ":expected": expected, **{f":v{i}": v for i, v in enumerate(extra.values())}}
    sets = ", ".join(["#s = :new", *[f"#f{i} = :v{i}" for i in range(len(extra))]])
    items = [
        {
            "Update": {
                "TableName": tables().transfers,
                "Key": _key(transfer_id),
                "UpdateExpression": f"SET {sets}",
                "ConditionExpression": "#s = :expected",
                "ExpressionAttributeNames": names,
                "ExpressionAttributeValues": values,
            }
        }
    ]
    if event:
        items.append({"Put": {"TableName": tables().outbox, "Item": outbox_item(event)}})
    try:
        aws.dynamodb_client().transact_write_items(TransactItems=items)
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "TransactionCanceledException":
            raise InvalidStateError(f"Transfer is not in state {expected}") from exc
        raise


def _event(event_type: str, t: dict[str, Any], correlation_id: str, **extra: Any) -> dict[str, Any]:
    data = {
        "transfer_id": t["transfer_id"],
        "customer_id": t["customer_id"],
        "source_account_id": t["source_account_id"],
        "destination_account_id": t["destination_account_id"],
        "amount_minor": t["amount_minor"],
        "currency": t["currency"],
        **extra,
    }
    return build_event(event_type, data, correlation_id=correlation_id, producer="transfer", entity_id=t["transfer_id"])


def _post(t: dict[str, Any], correlation_id: str) -> tuple[int, dict[str, Any]]:
    """Ask the ledger to post an APPROVED_FOR_POSTING transfer.

    Definitive ledger rejections move the transfer to REJECTED. Ambiguous
    failures (timeouts, conflicts) leave it in APPROVED_FOR_POSTING so that a
    retry with the same idempotency key — or the stuck-transfer sweeper — can
    resume. Re-posting is safe because the ledger journal id is the transfer id.
    """

    try:
        clients.ledger().call(
            "post_transfer",
            {
                "transfer_id": t["transfer_id"],
                "source_account_id": t["source_account_id"],
                "destination_account_id": t["destination_account_id"],
                "amount_minor": t["amount_minor"],
                "currency": t["currency"],
                "customer_id": t["customer_id"],
                "correlation_id": correlation_id,
            },
        )
    except DEFINITIVE_LEDGER_ERRORS as err:
        _transition(
            t["transfer_id"],
            "APPROVED_FOR_POSTING",
            "REJECTED",
            extra={"reason_code": err.code},
            event=_event("TransferRejected", t, correlation_id, reason_code=err.code, status="REJECTED"),
        )
        metrics.emit("TransferRejected", Reason=err.code)
        return err.status, {**err.to_body(correlation_id), "transfer": public_view(load_transfer(t["transfer_id"]) or t)}
    except InvalidStateError:
        pass  # already posted by a concurrent resume; fall through and report state
    current = load_transfer(t["transfer_id"]) or t
    if current["status"] == "COMPLETED":
        metrics.emit("TransferCompleted")
        return 201, public_view(current)
    raise ConcurrencyConflictError("Transfer posting outcome is pending; retry with the same Idempotency-Key")


def _validate_accounts(customer_id: str, source_id: str, dest_id: str, currency: str) -> tuple[dict[str, Any], dict[str, Any]]:
    acct = clients.account()
    try:
        source = acct.call("get_for_transfer", {"account_id": source_id})
    except NotFoundError:
        source = None
    if source is None or source["customer_id"] != customer_id:
        raise NotFoundError("Source account not found")
    try:
        dest = acct.call("get_for_transfer", {"account_id": dest_id})
    except NotFoundError as exc:
        raise NotFoundError("Destination account not found") from exc
    for a in (source, dest):
        if a["status"] != "ACTIVE":
            raise AccountNotActiveError("Account is not active")
        if a["currency"] != currency:
            raise CurrencyMismatchError("Account currency does not match the transfer currency")
    return source, dest


def _screen_and_post(t: dict[str, Any], source: dict[str, Any], dest: dict[str, Any], correlation_id: str) -> tuple[int, dict[str, Any]]:
    try:
        decision = clients.fraud().call(
            "screen",
            {
                "transfer_id": t["transfer_id"],
                "customer_id": t["customer_id"],
                "source_account_id": t["source_account_id"],
                "destination_account_id": t["destination_account_id"],
                "destination_customer_id": dest["customer_id"],
                "amount_minor": t["amount_minor"],
                "currency": t["currency"],
                "request_fingerprint": t["request_fingerprint"],
                "source_account_created_at": source["created_at"],
            },
        )
    except BankingError as err:
        # Fail closed: without a screening decision nothing may be posted.
        _transition(
            t["transfer_id"],
            "SCREENING",
            "FAILED",
            extra={"reason_code": "FRAUD_SCREENING_UNAVAILABLE"},
            event=_event("TransferRejected", t, correlation_id, reason_code="FRAUD_SCREENING_UNAVAILABLE", status="FAILED"),
        )
        metrics.emit("TransferFailedClosed")
        failure = DependencyUnavailableError("Fraud screening unavailable; the transfer was not posted")
        failure.details = {"cause": err.code}
        return failure.status, {**failure.to_body(correlation_id), "transfer": public_view(load_transfer(t["transfer_id"]) or t)}

    fraud_fields = {
        "fraud_decision": decision["decision"],
        "fraud_decision_id": decision["decision_id"],
        "fraud_decision_sk": decision["decision_sk"],
        "risk_score": decision["risk_score"],
        "triggered_rules": decision["triggered_rules"],
        "policy_version": decision["policy_version"],
    }
    if decision["decision"] == "REJECTED":
        _transition(
            t["transfer_id"],
            "SCREENING",
            "REJECTED",
            extra={**fraud_fields, "reason_code": "FRAUD_POLICY"},
            event=_event("TransferRejected", t, correlation_id, reason_code="FRAUD_POLICY", status="REJECTED"),
        )
        metrics.emit("TransferRejected", Reason="FRAUD_POLICY")
        return 422, {
            "error": {"code": "TRANSFER_REJECTED", "message": "Transfer was declined by risk screening", "correlation_id": correlation_id},
            "transfer": public_view(load_transfer(t["transfer_id"])),
        }
    if decision["decision"] == "PENDING_REVIEW":
        _transition(
            t["transfer_id"],
            "SCREENING",
            "PENDING_REVIEW",
            extra={**fraud_fields, "review_queue": "PENDING_REVIEW"},
            event=_event("TransferPendingReview", t, correlation_id, status="PENDING_REVIEW", risk_score=decision["risk_score"]),
        )
        metrics.emit("TransferPendingReview")
        return 202, public_view(load_transfer(t["transfer_id"]))
    _transition(t["transfer_id"], "SCREENING", "APPROVED_FOR_POSTING", extra=fraud_fields)
    return _post({**t, **fraud_fields, "status": "APPROVED_FOR_POSTING"}, correlation_id)


@router.route("POST /v1/transfers")
def create_transfer(req: Request) -> tuple[int, Any]:
    req.principal.require_scope(SCOPE_WRITE)
    key = validate_key(req.headers.get("idempotency-key"))
    body = validate_object(
        req.body or {},
        required={
            "source_account_id": string(pattern=ACCOUNT_ID_PATTERN),
            "destination_account_id": string(pattern=ACCOUNT_ID_PATTERN),
            "amount_minor": _amount,
            "currency": _currency,
        },
        optional={"memo": internal_safe_string(80)},
    )
    if body["source_account_id"] == body["destination_account_id"]:
        raise ValidationError("Source and destination accounts must be different")
    customer_id = customer_id_for(req.principal)
    req_hash = request_hash(body)
    store = IdempotencyStore()
    record = store.begin(customer_id, key, req_hash, new_id("TRF"))

    if not record.is_new:
        if record.status == "COMPLETED" and record.response:
            metrics.emit("IdempotentReplay")
            return int(record.response["status"]), record.response["body"]
        existing = load_transfer(record.resource_id) if record.resource_id else None
        if existing and existing["status"] == "APPROVED_FOR_POSTING":
            status, out = _post(existing, req.correlation_id)
            store.complete(customer_id, key, req_hash, {"status": status, "body": out})
            return status, out
        if existing and existing["status"] in TERMINAL | {"PENDING_REVIEW"}:
            out = public_view(existing)
            status = {"COMPLETED": 201, "PENDING_REVIEW": 202}.get(existing["status"], 422)
            return status, out
        raise RequestInProgressError("A request with this Idempotency-Key is still being processed")

    transfer_id = record.resource_id
    if transfer_id is None:  # pragma: no cover - begin() always assigns one
        raise InvalidStateError("Idempotency record has no transfer id")
    try:
        source, dest = _validate_accounts(customer_id, body["source_account_id"], body["destination_account_id"], body["currency"])
    except DependencyUnavailableError:
        # Nothing was created: release the key so the client can retry.
        aws.table(tables().idempotency).delete_item(
            Key={"PK": f"CUSTOMER#{customer_id}", "SK": f"REQUEST#{key}"},
            ConditionExpression="#s = :p",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":p": "IN_PROGRESS"},
        )
        raise
    except BankingError as err:
        store.complete(customer_id, key, req_hash, {"status": err.status, "body": err.to_body(req.correlation_id)})
        raise

    now = now_iso()
    t = {
        **_key(transfer_id),
        "GSI1PK": f"CUSTOMER#{customer_id}",
        "GSI1SK": f"CREATED#{now}#{transfer_id}",
        "transfer_id": transfer_id,
        "customer_id": customer_id,
        "initiator_subject": req.principal.subject,
        "source_account_id": body["source_account_id"],
        "destination_account_id": body["destination_account_id"],
        "destination_customer_id": dest["customer_id"],
        "amount_minor": body["amount_minor"],
        "currency": body["currency"],
        "memo": body.get("memo"),
        "idempotency_key_hash": request_hash({"key": key}),
        "status": "SCREENING",
        "created_at": now,
        "updated_at": now,
        "correlation_id": req.correlation_id,
    }
    t["request_fingerprint"] = fingerprint(t)
    aws.dynamodb_client().transact_write_items(
        TransactItems=[
            {"Put": {"TableName": tables().transfers, "Item": t, "ConditionExpression": "attribute_not_exists(PK)"}},
            {
                "Put": {
                    "TableName": tables().outbox,
                    "Item": outbox_item(_event("TransferRequested", t, req.correlation_id, status="SCREENING")),
                }
            },
        ]
    )
    metrics.emit("TransferRequested")
    try:
        status, out = _screen_and_post(t, source, dest, req.correlation_id)
    except ConcurrencyConflictError:
        raise  # leave the idempotency record IN_PROGRESS: retry resumes posting
    store.complete(customer_id, key, req_hash, {"status": status, "body": out})
    return status, out


@router.route("GET /v1/transfers/{id}")
def get_transfer(req: Request) -> tuple[int, Any]:
    req.principal.require_scope(SCOPE_READ)
    transfer_id = path_id(req.path_params.get("id"), TRANSFER_ID_PATTERN, "transfer id")
    t = load_transfer(transfer_id)
    is_reviewer = req.principal.is_member(GROUP_FRAUD_REVIEWERS) and SCOPE_ADMIN in req.principal.scopes
    if t is None:
        raise NotFoundError("Transfer not found")
    if not is_reviewer and t["customer_id"] != customer_id_for(req.principal, required=False):
        raise NotFoundError("Transfer not found")
    return 200, public_view(t, reviewer=is_reviewer)


def _reviewer_checks(principal: Principal, t: dict[str, Any]) -> None:
    principal.require_scope(SCOPE_ADMIN)
    principal.require_group(GROUP_FRAUD_REVIEWERS)
    if principal.subject == t["initiator_subject"]:
        raise SeparationOfDutiesError("Reviewers cannot approve or reject their own transfers")
    reviewer_customer = customer_id_for(principal, required=False)
    if reviewer_customer and reviewer_customer in {t["customer_id"], t.get("destination_customer_id")}:
        raise SeparationOfDutiesError("Reviewers cannot review transfers involving their own accounts")


def _review_body(req: Request) -> dict[str, Any]:
    return validate_object(req.body or {}, required={}, optional={"reason": internal_safe_string(200)})


@router.route("POST /v1/admin/transfers/{id}/approve")
def approve(req: Request) -> tuple[int, Any]:
    req.principal.require_scope(SCOPE_ADMIN)
    req.principal.require_group(GROUP_FRAUD_REVIEWERS)
    body = _review_body(req)
    transfer_id = path_id(req.path_params.get("id"), TRANSFER_ID_PATTERN, "transfer id")
    t = load_transfer(transfer_id)
    if t is None:
        raise NotFoundError("Transfer not found")
    _reviewer_checks(req.principal, t)
    if t["status"] != "PENDING_REVIEW":
        raise InvalidStateError("Only transfers in PENDING_REVIEW can be approved")

    # --- Revalidation before posting -----------------------------------
    if fingerprint(t) != t["request_fingerprint"]:
        metrics.emit("TransferIntegrityFailure")
        raise InvalidStateError("Transfer integrity check failed")
    decision = clients.fraud().call("get_decision", {"customer_id": t["customer_id"], "decision_sk": t["fraud_decision_sk"]})
    if (
        decision["decision"] != "PENDING_REVIEW"
        or decision["transfer_id"] != transfer_id
        or decision["request_fingerprint"] != t["request_fingerprint"]
        or decision.get("alert_status") != "OPEN"
    ):
        raise InvalidStateError("Fraud decision is not valid for approval")
    if parse_iso(decision["review_expires_at"]) < parse_iso(now_iso()):
        raise InvalidStateError("Fraud review window has expired; the customer must submit a new transfer")
    _validate_accounts(t["customer_id"], t["source_account_id"], t["destination_account_id"], t["currency"])

    reviewed = {"reviewed_by": req.principal.subject, "reviewed_at": now_iso(), "review_reason": body.get("reason")}
    _transition(transfer_id, "PENDING_REVIEW", "APPROVED_FOR_POSTING", extra=reviewed)
    clients.fraud().call(
        "record_review",
        {
            "customer_id": t["customer_id"],
            "decision_sk": t["fraud_decision_sk"],
            "outcome": "APPROVED",
            "reviewer": req.principal.subject,
            "destination_account_id": t["destination_account_id"],
        },
    )
    status, out = _post({**t, "status": "APPROVED_FOR_POSTING"}, req.correlation_id)
    if status == 201:
        out = public_view(load_transfer(transfer_id), reviewer=True)
    return (200 if status == 201 else status), out


@router.route("POST /v1/admin/transfers/{id}/reject")
def reject(req: Request) -> tuple[int, Any]:
    req.principal.require_scope(SCOPE_ADMIN)
    req.principal.require_group(GROUP_FRAUD_REVIEWERS)
    body = _review_body(req)
    transfer_id = path_id(req.path_params.get("id"), TRANSFER_ID_PATTERN, "transfer id")
    t = load_transfer(transfer_id)
    if t is None:
        raise NotFoundError("Transfer not found")
    _reviewer_checks(req.principal, t)
    if t["status"] != "PENDING_REVIEW":
        raise InvalidStateError("Only transfers in PENDING_REVIEW can be rejected")
    _transition(
        transfer_id,
        "PENDING_REVIEW",
        "REJECTED",
        extra={
            "reviewed_by": req.principal.subject,
            "reviewed_at": now_iso(),
            "review_reason": body.get("reason"),
            "reason_code": "REVIEW_REJECTED",
        },
        event=_event("TransferRejected", t, req.correlation_id, reason_code="REVIEW_REJECTED", status="REJECTED"),
    )
    clients.fraud().call(
        "record_review",
        {"customer_id": t["customer_id"], "decision_sk": t["fraud_decision_sk"], "outcome": "REJECTED", "reviewer": req.principal.subject},
    )
    return 200, public_view(load_transfer(transfer_id), reviewer=True)


# ------------------------------------------------------------------ internal
def resume_posting(p: dict[str, Any]) -> dict[str, Any]:
    """Used by the stuck-transfer runbook: re-drive APPROVED_FOR_POSTING transfers."""

    t = load_transfer(path_id(p.get("transfer_id"), TRANSFER_ID_PATTERN, "transfer_id"))
    if t is None:
        raise NotFoundError("Transfer not found")
    if t["status"] != "APPROVED_FOR_POSTING":
        return public_view(t)
    _, out = _post(t, p.get("correlation_id") or "resume")
    return out if "transfer_id" in out else out.get("transfer", out)


def internal(request: dict[str, Any]) -> dict[str, Any]:
    return clients.internal_dispatch({"resume_posting": resume_posting}, request)


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    if "routeKey" in event:
        return router(event, context)
    if not isinstance(event, dict) or "action" not in event:
        raise ForbiddenError("Unsupported invocation")
    return internal(event)
