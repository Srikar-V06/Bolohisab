import sqlite3
from dataclasses import dataclass
from secrets import token_urlsafe

from .ledger import EntryType, PaymentMethodCode
from .localization import LanguageCode


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
    language: LanguageCode | None
    share_token: str | None


class ReceiptNotFound(LookupError):
    pass


def list_receipt_items(
    connection: sqlite3.Connection, shop_id: int, customer_id: int | None = None,
) -> list[ReceiptItem]:
    rows = connection.execute(
        """
        SELECT entry.id AS entry_id, shop.name AS shop_name, entry.customer_id,
               customer.name AS customer_name, entry.type, entry.amount_paise,
               entry.balance_effect_paise, entry.payment_method, entry.created_at,
               receipt.issued_at, receipt.sent_at, receipt.language, receipt.share_token
        FROM ledger_entries AS entry
        JOIN customers AS customer ON customer.shop_id = entry.shop_id AND customer.id = entry.customer_id
        JOIN shops AS shop ON shop.id = entry.shop_id
        LEFT JOIN receipts AS receipt ON receipt.ledger_entry_id = entry.id AND receipt.shop_id = entry.shop_id
        WHERE entry.shop_id = ? AND (? IS NULL OR entry.customer_id = ?)
        ORDER BY entry.id
        """,
        (shop_id, customer_id, customer_id),
    )
    balances: dict[int, int] = {}
    items = []
    for row in rows:
        values = dict(row)
        customer = values["customer_id"]
        balances[customer] = balances.get(customer, 0) + values.pop("balance_effect_paise")
        language = values.pop("language")
        items.append(ReceiptItem(
            **values, balance_after_paise=balances[customer],
            language=LanguageCode(language) if language is not None else None,
        ))
    return items[::-1]


def _entry_item(connection: sqlite3.Connection, shop_id: int, entry_id: int) -> ReceiptItem:
    entry = connection.execute(
        "SELECT customer_id FROM ledger_entries WHERE shop_id = ? AND id = ?", (shop_id, entry_id),
    ).fetchone()
    if entry is None:
        raise ReceiptNotFound()
    return next(item for item in list_receipt_items(connection, shop_id, entry["customer_id"])
                if item.entry_id == entry_id)


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
        return _entry_item(connection, shop_id, entry_id)
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
    receipt = connection.execute(
        "SELECT shop_id, ledger_entry_id FROM receipts WHERE share_token = ?", (token,),
    ).fetchone()
    if receipt is None:
        raise ReceiptNotFound()
    return _entry_item(connection, receipt["shop_id"], receipt["ledger_entry_id"])
