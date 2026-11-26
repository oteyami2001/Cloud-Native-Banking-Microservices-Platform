"""Double-entry ledger engine — the only component allowed to change balances.

Accounting model (see docs/banking-business-model.md):

* Customer deposit accounts are **liabilities** of the bank and are
  credit-normal: a credit increases the balance, a debit decreases it.
* ``GL-1000 Synthetic Funding`` is an **asset**, debit-normal. Opening
  balances are posted as ``Dr GL-1000 / Cr customer deposit``, so total
  assets always equal total customer liabilities.
* An internal transfer is ``Dr source deposit / Cr destination deposit``.
* Reversals are new compensating journals; entries are never updated or
  deleted.

Every posting is a single DynamoDB ``TransactWriteItems`` call containing, for
each journal line, a conditional balance update and an immutable entry, plus a
journal header, a permanent posting-idempotency record, an optional transfer
state transition and a transactional-outbox event. Either everything commits
or nothing does.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any, Literal

from botocore.exceptions import ClientError

from shared import aws, metrics
from shared.config import GL_SYNTHETIC_FUNDING_ACCOUNT, tables
from shared.contracts import build_event, outbox_item
from shared.errors import (
    AccountNotActiveError,
    ConcurrencyConflictError,
    CurrencyMismatchError,
    IdempotencyKeyReusedError,
    InsufficientFundsError,
    InvalidStateError,
    NotFoundError,
    ValidationError,
)
from shared.ids import now_iso
from shared.logging import get_correlation_id
from shared.money import MAX_BALANCE_MINOR, validate_amount_minor, validate_currency

Side = Literal["D", "C"]
ACTIVE = "ACTIVE"
MAX_CONFLICT_RETRIES = 4


@dataclass(frozen=True)
class Line:
    account_id: str
    side: Side
    amount_minor: int


@dataclass(frozen=True)
class StateGuard:
    """Optional conditional state transition committed with the posting."""

    transfer_id: str
    expected_status: str
    new_status: str


@dataclass(frozen=True)
class PostingResult:
    journal_id: str
    posted_at: str
    replayed: bool


def _balance_key(account_id: str) -> dict[str, str]:
    return {"PK": f"ACCOUNT#{account_id}", "SK": "BALANCE"}


def _journal_hash(journal_type: str, currency: str, lines: list[Line]) -> str:
    canonical = json.dumps(
        {"type": journal_type, "currency": currency, "lines": [[ln.account_id, ln.side, ln.amount_minor] for ln in lines]},
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


class Ledger:
    def __init__(self) -> None:
        self.t = tables()
        self.ledger = aws.table(self.t.ledger)
        self.client = aws.dynamodb_client()

    # ------------------------------------------------------------------ accounts
    def open_account(
        self,
        account_id: str,
        *,
        customer_id: str | None,
        currency: str,
        account_class: Literal["LIABILITY", "ASSET"] = "LIABILITY",
    ) -> dict[str, Any]:
        """Create a zero balance record. Idempotent for identical parameters."""

        validate_currency(currency)
        item = {
            **_balance_key(account_id),
            "account_id": account_id,
            "customer_id": customer_id,
            "account_class": account_class,
            "normal_side": "C" if account_class == "LIABILITY" else "D",
            "currency": currency,
            "available_balance_minor": 0,
            "version": 0,
            "status": ACTIVE,
            "created_at": now_iso(),
        }
        try:
            self.ledger.put_item(Item=item, ConditionExpression="attribute_not_exists(PK)")
            return self._public_balance(item)
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
        existing = self.get_balance_record(account_id)
        if existing["customer_id"] != customer_id or existing["currency"] != currency:
            raise InvalidStateError("Ledger account already exists with different attributes")
        return self._public_balance(existing)

    def set_status(self, account_id: str, status: str) -> dict[str, Any]:
        if status not in {"ACTIVE", "FROZEN", "CLOSED"}:
            raise ValidationError("Unsupported account status")
        try:
            result = self.ledger.update_item(
                Key=_balance_key(account_id),
                UpdateExpression="SET #s = :s, version = version + :one, updated_at = :now",
                ConditionExpression="attribute_exists(PK) AND (#s <> :closed)",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":s": status, ":one": 1, ":now": now_iso(), ":closed": "CLOSED"},
                ReturnValues="ALL_NEW",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise InvalidStateError("Account does not exist or is closed") from exc
            raise
        return self._public_balance(aws.to_native(result["Attributes"]))

    def get_balance_record(self, account_id: str) -> dict[str, Any]:
        # Strongly consistent: balances are authoritative financial data.
        item = self.ledger.get_item(Key=_balance_key(account_id), ConsistentRead=True).get("Item")
        if not item:
            raise NotFoundError("Ledger account not found")
        return aws.to_native(item)

    @staticmethod
    def _public_balance(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "account_id": item["account_id"],
            "currency": item["currency"],
            "available_balance_minor": int(item["available_balance_minor"]),
            "status": item["status"],
            "version": int(item["version"]),
        }

    def get_balance(self, account_id: str) -> dict[str, Any]:
        return self._public_balance(self.get_balance_record(account_id))

    def list_entries(self, account_id: str, *, limit: int = 25, start_key: dict[str, Any] | None = None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "KeyConditionExpression": "PK = :pk AND begins_with(SK, :entry)",
            "ExpressionAttributeValues": {":pk": f"ACCOUNT#{account_id}", ":entry": "ENTRY#"},
            "ScanIndexForward": False,
            "Limit": limit,
            "ConsistentRead": True,
        }
        if start_key:
            kwargs["ExclusiveStartKey"] = start_key
        result = self.ledger.query(**kwargs)
        entries = [{k: v for k, v in aws.to_native(item).items() if k not in {"PK", "SK"}} for item in result.get("Items", [])]
        return {"entries": entries, "last_key": result.get("LastEvaluatedKey")}

    # ----------------------------------------------------------------- postings
    def post_journal(
        self,
        *,
        journal_id: str,
        journal_type: str,
        currency: str,
        lines: list[Line],
        description: str,
        correlation_id: str | None,
        owner_check: tuple[str, str] | None = None,
        state_guard: StateGuard | None = None,
        event: tuple[str, dict[str, Any]] | None = None,
        transfer_id: str | None = None,
    ) -> PostingResult:
        """Atomically post a balanced journal.

        ``owner_check`` = (account_id, customer_id) adds a defense-in-depth
        condition that the debited customer account belongs to the customer
        who authorised the transfer.
        """

        validate_currency(currency)
        correlation_id = correlation_id or get_correlation_id()
        if len(lines) < 2:
            raise ValidationError("A journal requires at least two lines")
        for ln in lines:
            validate_amount_minor(ln.amount_minor, maximum=MAX_BALANCE_MINOR)
            if ln.side not in ("D", "C"):
                raise ValidationError("Journal line side must be D or C")
        if len({ln.account_id for ln in lines}) != len(lines):
            raise ValidationError("A journal cannot reference the same account twice")
        debits = sum(ln.amount_minor for ln in lines if ln.side == "D")
        credits = sum(ln.amount_minor for ln in lines if ln.side == "C")
        if debits != credits:
            raise ValidationError("Journal is not balanced")

        jhash = _journal_hash(journal_type, currency, lines)
        attempt = 0
        while True:
            # Normal-side metadata is immutable, so reading it outside the
            # transaction is safe; balances are only changed by the conditions.
            records = {ln.account_id: self.get_balance_record(ln.account_id) for ln in lines}
            posted_at = now_iso()
            items = self._build_items(
                journal_id,
                journal_type,
                currency,
                lines,
                description,
                correlation_id,
                owner_check,
                state_guard,
                event,
                transfer_id,
                jhash,
                posted_at,
                records,
            )
            try:
                self.client.transact_write_items(TransactItems=items)
                metrics.emit("JournalPosted", JournalType=journal_type)
                return PostingResult(journal_id, posted_at, False)
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "TransactionCanceledException":
                    raise
                reasons = [r.get("Code", "None") for r in exc.response.get("CancellationReasons", [])]
                if "TransactionConflict" in reasons and attempt < MAX_CONFLICT_RETRIES:
                    attempt += 1
                    metrics.emit("LedgerTransactionConflict")
                    time.sleep(min(0.4, 0.02 * 2**attempt) * secrets.randbelow(1000) / 1000)  # full jitter
                    continue
                return self._diagnose_failure(journal_id, jhash, currency, lines, owner_check, state_guard, reasons)

    def _build_items(
        self,
        journal_id,
        journal_type,
        currency,
        lines,
        description,
        correlation_id,
        owner_check,
        state_guard,
        event,
        transfer_id,
        jhash,
        posted_at,
        records,
    ) -> list[dict[str, Any]]:
        t = self.t
        items: list[dict[str, Any]] = []
        for idx, ln in enumerate(lines):
            record = records[ln.account_id]
            delta = ln.amount_minor if ln.side == record["normal_side"] else -ln.amount_minor
            names = {"#s": "status", "#b": "available_balance_minor"}
            values: dict[str, Any] = {":delta": delta, ":one": 1, ":active": ACTIVE, ":cur": currency, ":now": posted_at}
            condition = "attribute_exists(PK) AND #s = :active AND currency = :cur"
            if delta < 0:
                # No account may go negative: covers customer overdraft and
                # protects the synthetic funding account.
                condition += " AND #b >= :needed"
                values[":needed"] = ln.amount_minor
            else:
                condition += " AND #b <= :ceiling"
                values[":ceiling"] = MAX_BALANCE_MINOR - ln.amount_minor
            if owner_check and owner_check[0] == ln.account_id:
                condition += " AND customer_id = :owner"
                values[":owner"] = owner_check[1]
            items.append(
                {
                    "Update": {
                        "TableName": t.ledger,
                        "Key": _balance_key(ln.account_id),
                        "UpdateExpression": "SET #b = #b + :delta, version = version + :one, updated_at = :now",
                        "ConditionExpression": condition,
                        "ExpressionAttributeNames": names,
                        "ExpressionAttributeValues": values,
                    }
                }
            )
            counterparties = [o.account_id for o in lines if o.account_id != ln.account_id]
            items.append(
                {
                    "Put": {
                        "TableName": t.ledger,
                        "Item": {
                            "PK": f"ACCOUNT#{ln.account_id}",
                            "SK": f"ENTRY#{posted_at}#{journal_id}#{idx}",
                            "entry_id": f"{journal_id}#{idx}",
                            "journal_id": journal_id,
                            "journal_type": journal_type,
                            "transfer_id": transfer_id,
                            "side": ln.side,
                            "direction": "CREDIT" if ln.side == "C" else "DEBIT",
                            "amount_minor": ln.amount_minor,
                            "signed_amount_minor": delta,
                            "currency": currency,
                            "counterparty_account_id": counterparties[0] if len(counterparties) == 1 else None,
                            "description": description,
                            "posted_at": posted_at,
                        },
                        "ConditionExpression": "attribute_not_exists(PK)",
                    }
                }
            )
        items.append(
            {
                "Put": {
                    "TableName": t.ledger,
                    "Item": {
                        "PK": f"JOURNAL#{journal_id}",
                        "SK": "HEADER",
                        "journal_id": journal_id,
                        "journal_type": journal_type,
                        "currency": currency,
                        "total_minor": sum(ln.amount_minor for ln in lines if ln.side == "D"),
                        "lines": [{"account_id": ln.account_id, "side": ln.side, "amount_minor": ln.amount_minor} for ln in lines],
                        "transfer_id": transfer_id,
                        "journal_hash": jhash,
                        "correlation_id": correlation_id,
                        "posted_at": posted_at,
                    },
                    "ConditionExpression": "attribute_not_exists(PK)",
                }
            }
        )
        items.append(
            {
                "Put": {
                    "TableName": t.idempotency,
                    "Item": {
                        "PK": f"POSTING#{journal_id}",
                        "SK": "LEDGER",
                        "journal_hash": jhash,
                        "status": "POSTED",
                        "posted_at": posted_at,
                    },
                    "ConditionExpression": "attribute_not_exists(PK)",
                }
            }
        )
        if state_guard:
            items.append(
                {
                    "Update": {
                        "TableName": t.transfers,
                        "Key": {"PK": f"TRANSFER#{state_guard.transfer_id}", "SK": "METADATA"},
                        "UpdateExpression": "SET #s = :new, posted_at = :now, journal_id = :j, updated_at = :now",
                        "ConditionExpression": "#s = :expected",
                        "ExpressionAttributeNames": {"#s": "status"},
                        "ExpressionAttributeValues": {
                            ":new": state_guard.new_status,
                            ":expected": state_guard.expected_status,
                            ":now": posted_at,
                            ":j": journal_id,
                        },
                    }
                }
            )
        if event:
            event_type, data = event
            envelope = build_event(
                event_type,
                {**data, "journal_id": journal_id, "posted_at": posted_at},
                correlation_id=correlation_id,
                producer="ledger",
                entity_id=transfer_id or journal_id,
            )
            items.append({"Put": {"TableName": t.outbox, "Item": outbox_item(envelope), "ConditionExpression": "attribute_not_exists(PK)"}})
        return items

    def _diagnose_failure(self, journal_id, jhash, currency, lines, owner_check, state_guard, reasons) -> PostingResult:
        """Translate a cancelled transaction into a precise domain error.

        Nothing was written, so a fresh strongly consistent read is safe.
        """

        header = self.ledger.get_item(Key={"PK": f"JOURNAL#{journal_id}", "SK": "HEADER"}, ConsistentRead=True).get("Item")
        if header:
            if header["journal_hash"] != jhash:
                raise IdempotencyKeyReusedError("Journal id was already posted with different lines")
            metrics.emit("DuplicatePostingPrevented")
            return PostingResult(journal_id, header["posted_at"], True)
        for ln in lines:
            rec = self.get_balance_record(ln.account_id)
            if rec["status"] != ACTIVE:
                raise AccountNotActiveError(f"Account {ln.account_id} is not active")
            if rec["currency"] != currency:
                raise CurrencyMismatchError("Account currency does not match the transfer currency")
            if owner_check and owner_check[0] == ln.account_id and rec.get("customer_id") != owner_check[1]:
                raise NotFoundError("Account not found")
            delta = ln.amount_minor if ln.side == rec["normal_side"] else -ln.amount_minor
            if delta < 0 and rec["available_balance_minor"] < ln.amount_minor:
                metrics.emit("InsufficientFunds")
                raise InsufficientFundsError("Insufficient available balance")
        if state_guard:
            raise InvalidStateError("Transfer is not in a state that permits posting")
        if "TransactionConflict" in reasons:
            raise ConcurrencyConflictError("Concurrent update conflict; retry the request")
        raise ConcurrencyConflictError("Posting conditions changed concurrently; retry the request")

    # ---------------------------------------------------------- business helpers
    def post_opening_balance(self, account_id: str, amount_minor: int, currency: str, correlation_id: str | None) -> PostingResult:
        validate_amount_minor(amount_minor)
        return self.post_journal(
            journal_id=f"OPEN-{account_id}",
            journal_type="OPENING_BALANCE",
            currency=currency,
            lines=[Line(GL_SYNTHETIC_FUNDING_ACCOUNT, "D", amount_minor), Line(account_id, "C", amount_minor)],
            description="Synthetic opening balance (sandbox)",
            correlation_id=correlation_id,
            event=("OpeningBalancePosted", {"account_id": account_id, "amount_minor": amount_minor, "currency": currency}),
        )

    def post_transfer(
        self,
        *,
        transfer_id: str,
        source_account_id: str,
        destination_account_id: str,
        amount_minor: int,
        currency: str,
        customer_id: str,
        correlation_id: str | None,
        expected_status: str = "APPROVED_FOR_POSTING",
    ) -> PostingResult:
        validate_amount_minor(amount_minor)
        if source_account_id == destination_account_id:
            raise ValidationError("Source and destination accounts must differ")
        dest = self.get_balance_record(destination_account_id)
        return self.post_journal(
            journal_id=transfer_id,
            journal_type="TRANSFER",
            currency=currency,
            lines=[Line(source_account_id, "D", amount_minor), Line(destination_account_id, "C", amount_minor)],
            description="Internal transfer",
            correlation_id=correlation_id,
            owner_check=(source_account_id, customer_id),
            state_guard=StateGuard(transfer_id, expected_status, "COMPLETED"),
            transfer_id=transfer_id,
            event=(
                "TransferCompleted",
                {
                    "transfer_id": transfer_id,
                    "source_account_id": source_account_id,
                    "destination_account_id": destination_account_id,
                    "amount_minor": amount_minor,
                    "currency": currency,
                    "source_customer_id": customer_id,
                    "destination_customer_id": dest.get("customer_id"),
                    "status": "COMPLETED",
                },
            ),
        )

    def reverse_transfer(self, transfer_id: str, *, reason: str, operator: str, correlation_id: str | None) -> PostingResult:
        """Compensating journal for an authorised reversal. Never deletes entries."""

        header = self.ledger.get_item(Key={"PK": f"JOURNAL#{transfer_id}", "SK": "HEADER"}, ConsistentRead=True).get("Item")
        if not header or header["journal_type"] != "TRANSFER":
            raise NotFoundError("Posted transfer not found")
        header = aws.to_native(header)
        original = {ln["side"]: ln for ln in header["lines"]}
        amount = original["D"]["amount_minor"]
        return self.post_journal(
            journal_id=f"REV-{transfer_id}",
            journal_type="REVERSAL",
            currency=header["currency"],
            lines=[Line(original["C"]["account_id"], "D", amount), Line(original["D"]["account_id"], "C", amount)],
            description=f"Reversal of {transfer_id}: {reason[:120]}",
            correlation_id=correlation_id,
            transfer_id=transfer_id,
            event=(
                "TransferReversed",
                {"transfer_id": transfer_id, "amount_minor": amount, "currency": header["currency"], "operator": operator},
            ),
        )
