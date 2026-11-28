import logging
import sqlite3
from dataclasses import dataclass
from re import fullmatch
from secrets import token_urlsafe
from typing import Literal

from .ledger import MAX_SQLITE_INTEGER, EntryType, Ledger, LedgerEntryDraft, PaymentMethodCode
from .localization import LanguageCode


ReceiptStatus = Literal["AWAITING", "GENERATED", "SENT", "CONFIRMED", "DISPUTED"]
DisputeStatus = Literal["PENDING", "APPROVED", "REJECTED"]
DisputeDecision = Literal["APPROVED", "REJECTED"]


@dataclass(frozen=True)
class ReceiptDispute:
    id: int
    claimed_amount_paise: int
    adjustment_paise: int
    reason: str
    status: DisputeStatus
    created_at: str
    reviewed_by: str | None
    reviewed_by_user_id: int | None
    reviewed_at: str | None
    adjustment_entry_id: int | None


@dataclass(frozen=True)
class ReceiptItem:
    entry_id: int
    shop_name: str
    customer_id: int
    customer_name: str
    type: EntryType
    amount_paise: int
    payment_method: PaymentMethodCode | None
    created_at: str
    balance_after_paise: int
    issued_at: str | None
    sent_at: str | None
    confirmed_at: str | None
    language: LanguageCode | None
    share_token: str | None
    receipt_id: int | None
    status: ReceiptStatus
    dispute: ReceiptDispute | None


class ReceiptNotFound(LookupError):
    pass


class ReceiptConflict(ValueError):
    pass


def _change_in_balance(entry_type: EntryType, amount_paise: int, claimed_amount_paise: int) -> int:
    difference = claimed_amount_paise - amount_paise
    return -difference if entry_type == "PAYMENT" else difference


def list_receipt_items(
    connection: sqlite3.Connection, shop_id: int, customer_id: int | None = None,
) -> list[ReceiptItem]:
    return _read_items(connection, shop_id, customer_id)


def _read_items(
    connection: sqlite3.Connection, shop_id: int, customer_id: int | None, through_entry: int | None = None,
) -> list[ReceiptItem]:
    rows = connection.execute(
        """
        SELECT entry.id AS entry_id, shop.name AS shop_name, entry.customer_id,
               customer.name AS customer_name, entry.type, entry.amount_paise,
               entry.balance_effect_paise, entry.payment_method, entry.created_at,
               receipt.id AS receipt_id, receipt.issued_at, receipt.sent_at, receipt.confirmed_at,
               receipt.language, receipt.share_token, dispute.id AS dispute_id,
               dispute.claimed_amount_paise, dispute.reason, dispute.status AS dispute_status,
               dispute.created_at AS requested_at, dispute.reviewed_by, dispute.reviewed_by_user_id, dispute.reviewed_at,
               dispute.adjustment_entry_id
        FROM ledger_entries AS entry
        JOIN customers AS customer ON customer.shop_id = entry.shop_id AND customer.id = entry.customer_id
        JOIN shops AS shop ON shop.id = entry.shop_id
        LEFT JOIN receipts AS receipt ON receipt.ledger_entry_id = entry.id AND receipt.shop_id = entry.shop_id
        LEFT JOIN correction_requests AS dispute ON dispute.original_entry_id = entry.id
            AND dispute.shop_id = entry.shop_id AND dispute.claimed_amount_paise IS NOT NULL
        WHERE entry.shop_id = ? AND (? IS NULL OR entry.customer_id = ?)
          AND (? IS NULL OR entry.id <= ?)
        ORDER BY entry.id
        """,
        (shop_id, customer_id, customer_id, through_entry, through_entry),
    )
    balances: dict[int, int] = {}
    items = []
    for row in rows:
        values = dict(row)
        customer = values["customer_id"]
        balances[customer] = balances.get(customer, 0) + values.pop("balance_effect_paise")
        language = values.pop("language")
        dispute_id, claim, reason, dispute_status, requested_at, reviewer, reviewer_id, reviewed_at, adjustment = (
            values.pop(key) for key in (
                "dispute_id", "claimed_amount_paise", "reason", "dispute_status", "requested_at",
                "reviewed_by", "reviewed_by_user_id", "reviewed_at", "adjustment_entry_id",
            )
        )
        dispute = None
        if dispute_id is not None:
            dispute = ReceiptDispute(
                dispute_id, claim, _change_in_balance(values["type"], values["amount_paise"], claim),
                reason, dispute_status, requested_at, reviewer, reviewer_id, reviewed_at, adjustment,
            )
        status: ReceiptStatus
        if dispute:
            status = "DISPUTED"
        elif values["confirmed_at"]:
            status = "CONFIRMED"
        elif values["sent_at"]:
            status = "SENT"
        elif values["receipt_id"]:
            status = "GENERATED"
        else:
            status = "AWAITING"
        items.append(ReceiptItem(
            **values, balance_after_paise=balances[customer], status=status, dispute=dispute,
            language=LanguageCode(language) if language is not None else None,
        ))
    return items[::-1]


def _entry_item(connection: sqlite3.Connection, shop_id: int, entry_id: int) -> ReceiptItem:
    entry = connection.execute(
        "SELECT customer_id FROM ledger_entries WHERE shop_id = ? AND id = ?", (shop_id, entry_id),
    ).fetchone()
    if entry is None:
        raise ReceiptNotFound()
    return _read_items(connection, shop_id, entry["customer_id"], through_entry=entry_id)[0]


def generate_receipt(
    connection: sqlite3.Connection, shop_id: int, entry_id: int, language: LanguageCode,
) -> ReceiptItem:
    item = _entry_item(connection, shop_id, entry_id)
    if item.share_token is None:
        connection.execute(
            """
            INSERT INTO receipts (shop_id, customer_id, ledger_entry_id, language, share_token)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(ledger_entry_id) DO UPDATE
                SET share_token = excluded.share_token, language = excluded.language
            """,
            (shop_id, item.customer_id, entry_id, language, token_urlsafe(32)),
        )
        item = _entry_item(connection, shop_id, entry_id)
        connection.execute("SAVEPOINT receipt_notification")
        try:
            connection.execute("""
                INSERT INTO notifications(customer_user_id,store_id,store_customer_id,receipt_id)
                SELECT customer_user_id,store_id,store_customer_id,? FROM store_customer_links
                WHERE store_id=? AND store_customer_id=? AND status='ACTIVE'
                ON CONFLICT(receipt_id,customer_user_id) DO NOTHING
            """, (item.receipt_id, shop_id, item.customer_id))
        except sqlite3.Error:
            connection.execute("ROLLBACK TO receipt_notification")
            logging.getLogger(__name__).exception("Notification failed for receipt %s", item.receipt_id)
        finally:
            connection.execute("RELEASE receipt_notification")
    return item


def mark_receipt_sent(connection: sqlite3.Connection, shop_id: int, entry_id: int) -> ReceiptItem:
    result = connection.execute(
        """
        UPDATE receipts
        SET sent_at = coalesce(sent_at, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        WHERE shop_id = ? AND ledger_entry_id = ? AND share_token IS NOT NULL
        """,
        (shop_id, entry_id),
    )
    if not result.rowcount:
        raise ReceiptNotFound()
    return _entry_item(connection, shop_id, entry_id)


def get_shared_receipt(connection: sqlite3.Connection, token: str) -> ReceiptItem:
    shop_id, entry_id = _resolve_share_token(connection, token)
    return _entry_item(connection, shop_id, entry_id)


def _resolve_share_token(connection: sqlite3.Connection, token: str) -> tuple[int, int]:
    if not fullmatch(r"[A-Za-z0-9_-]{43}", token):
        raise ReceiptNotFound()
    receipt = connection.execute(
        "SELECT shop_id, ledger_entry_id FROM receipts WHERE share_token = ?", (token,),
    ).fetchone()
    if receipt is None:
        raise ReceiptNotFound()
    return receipt["shop_id"], receipt["ledger_entry_id"]


def confirm_shared_receipt(connection: sqlite3.Connection, token: str) -> None:
    shop_id, entry_id = _resolve_share_token(connection, token)
    item = _entry_item(connection, shop_id, entry_id)
    if item.dispute:
        raise ReceiptConflict("RECEIPT_ALREADY_DISPUTED")
    connection.execute(
        """
        UPDATE receipts
        SET confirmed_at = coalesce(confirmed_at, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            sent_at = coalesce(sent_at, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        WHERE shop_id = ? AND ledger_entry_id = ?
        """,
        (shop_id, entry_id),
    )


def dispute_shared_receipt(
    connection: sqlite3.Connection, token: str, claimed_amount_paise: int, reason: str,
) -> None:
    shop_id, entry_id = _resolve_share_token(connection, token)
    item = _entry_item(connection, shop_id, entry_id)
    if item.confirmed_at:
        raise ReceiptConflict("RECEIPT_ALREADY_CONFIRMED")
    if item.dispute:
        if (item.dispute.claimed_amount_paise, item.dispute.reason) == (claimed_amount_paise, reason):
            return
        raise ReceiptConflict("RECEIPT_ALREADY_DISPUTED")
    change = _change_in_balance(item.type, item.amount_paise, claimed_amount_paise)
    if (
        abs(claimed_amount_paise) > MAX_SQLITE_INTEGER or not 1 <= abs(change) <= MAX_SQLITE_INTEGER
        or (item.type != "ADJUSTMENT" and claimed_amount_paise < 0)
    ):
        raise ReceiptConflict("INVALID_CLAIM")
    connection.execute(
        """
        INSERT INTO correction_requests (shop_id, customer_id, original_entry_id, reason, claimed_amount_paise)
        VALUES (?, ?, ?, ?, ?)
        """,
        (shop_id, item.customer_id, entry_id, reason, claimed_amount_paise),
    )
    mark_receipt_sent(connection, shop_id, entry_id)


def review_receipt_dispute(
    connection: sqlite3.Connection, shop_id: int, entry_id: int, decision: DisputeDecision, reviewer: str,
    reviewer_id: int,
) -> ReceiptItem:
    item = _entry_item(connection, shop_id, entry_id)
    dispute = item.dispute
    if dispute is None:
        raise ReceiptNotFound()
    if dispute.status == decision:
        return item
    if dispute.status != "PENDING":
        raise ReceiptConflict("DISPUTE_ALREADY_REVIEWED")

    adjustment_id = None
    if decision == "APPROVED":
        entry = Ledger(connection).create_ledger_entry(
            shop_id, f"receipt-dispute:{dispute.id}",
            LedgerEntryDraft(item.customer_id, "ADJUSTMENT", dispute.adjustment_paise, corrects_entry_id=entry_id),
        )
        adjustment_id = entry.id
    connection.execute(
        """
        UPDATE correction_requests
        SET status = ?, reviewed_by = ?, reviewed_by_user_id = ?, reviewed_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
            adjustment_entry_id = ?
        WHERE shop_id = ? AND id = ?
        """,
        (decision, reviewer, reviewer_id, adjustment_id, shop_id, dispute.id),
    )
    return _entry_item(connection, shop_id, entry_id)
