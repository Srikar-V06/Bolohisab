import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from itertools import chain, groupby
from pathlib import Path
from typing import Literal

from .database import database_transaction

MAX_SQLITE_INTEGER = 2**63 - 1
EntryType = Literal["CREDIT", "PAYMENT", "ADJUSTMENT"]
PaymentMethodCode = Literal["CASH", "UPI"]


class CustomerNotFound(LookupError):
    pass


class BatchConflict(ValueError):
    pass


def validate_customer_name(name: str) -> str:
    if not isinstance(name, str) or not name.strip() or len(name) > 120 or "\x00" in name:
        raise ValueError("Customer name must contain 1–120 characters and cannot be blank")
    return name


def validate_id(value: int, field: str) -> None:
    if type(value) is not int or not 1 <= value <= MAX_SQLITE_INTEGER:
        raise ValueError(f"{field} must be a positive integer within SQLite's range")


@dataclass(frozen=True)
class Customer:
    id: int
    shop_id: int
    name: str
    created_at: str
    balance_paise: int
    last_transaction_at: str | None = None


@dataclass(frozen=True)
class CustomerIdentity:
    id: int
    name: str


@dataclass(frozen=True)
class LedgerEntryDraft:
    customer_id: int
    type: EntryType
    amount_paise: int
    corrects_entry_id: int | None = None
    payment_method: PaymentMethodCode | None = None

    def __post_init__(self) -> None:
        validate_id(self.customer_id, "customer_id")
        if self.type not in ("CREDIT", "PAYMENT", "ADJUSTMENT"):
            raise ValueError("Unsupported ledger entry type")
        if type(self.amount_paise) is not int or not 1 <= abs(self.amount_paise) <= MAX_SQLITE_INTEGER:
            raise ValueError("amount_paise must be a nonzero integer within SQLite's range")
        if self.type != "ADJUSTMENT" and self.amount_paise < 0:
            raise ValueError("A credit or payment requires a positive amount_paise")
        if self.corrects_entry_id is not None:
            validate_id(self.corrects_entry_id, "corrects_entry_id")
            if self.type != "ADJUSTMENT":
                raise ValueError("Only an adjustment can correct an existing ledger entry")
        if self.payment_method is not None and (
            self.type != "PAYMENT" or self.payment_method not in ("CASH", "UPI")
        ):
            raise ValueError("Cash and UPI methods apply to payments only")

    @property
    def balance_effect_paise(self) -> int:
        return -self.amount_paise if self.type == "PAYMENT" else self.amount_paise


@dataclass(frozen=True)
class LedgerEntry:
    id: int
    shop_id: int
    batch_id: str
    customer_id: int
    type: EntryType
    amount_paise: int
    balance_effect_paise: int
    corrects_entry_id: int | None
    created_at: str
    original_transcript: str | None
    detected_language: str | None
    payment_method: PaymentMethodCode | None

    def as_draft(self) -> LedgerEntryDraft:
        return LedgerEntryDraft(
            self.customer_id, self.type, self.amount_paise, self.corrects_entry_id, self.payment_method,
        )


@dataclass(frozen=True)
class TransactionBatch:
    id: str
    shop_id: int
    created_at: str
    original_transcript: str | None
    detected_language: str | None
    entries: tuple[LedgerEntry, ...]


@contextmanager
def ledger_session(path: Path, *, write: bool = False) -> Iterator["Ledger"]:
    with database_transaction(path, write=write) as connection:
        yield Ledger(connection)


class Ledger:
    """Customer and ledger operations within one database transaction."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create_customer(self, shop_id: int, name: str) -> Customer:
        validate_id(shop_id, "shop_id")
        validate_customer_name(name)
        self._require_shop(shop_id)
        row = self.connection.execute(
            """
            INSERT INTO customers (shop_id, name) VALUES (?, ?)
            RETURNING id, shop_id, name, created_at
            """,
            (shop_id, name),
        ).fetchone()
        return Customer(**dict(row), balance_paise=0)

    def list_customers(self, shop_id: int) -> list[Customer]:
        validate_id(shop_id, "shop_id")
        return list(self._read_customers(shop_id))

    def list_customer_names(self, shop_id: int) -> list[CustomerIdentity]:
        validate_id(shop_id, "shop_id")
        rows = self.connection.execute(
            "SELECT id, name FROM customers WHERE shop_id = ? ORDER BY id",
            (shop_id,),
        )
        return [CustomerIdentity(**dict(row)) for row in rows]

    def get_customer(self, shop_id: int, customer_id: int) -> Customer:
        validate_id(shop_id, "shop_id")
        validate_id(customer_id, "customer_id")
        customer = next(self._read_customers(shop_id, customer_id), None)
        if customer is None:
            raise CustomerNotFound("Customer not found")
        return customer

    def calculate_balance(self, shop_id: int, customer_id: int) -> int:
        return self.get_customer(shop_id, customer_id).balance_paise

    def get_transaction_history(self, shop_id: int, customer_id: int) -> list[LedgerEntry]:
        validate_id(shop_id, "shop_id")
        validate_id(customer_id, "customer_id")
        self._require_customer(shop_id, customer_id)
        return self._read_entries(shop_id, customer_id=customer_id)

    def get_batch(self, shop_id: int, batch_id: str) -> TransactionBatch | None:
        row = self.connection.execute(
            "SELECT * FROM transaction_batches WHERE shop_id = ? AND id = ?",
            (shop_id, batch_id),
        ).fetchone()
        if row is None:
            return None
        entries = tuple(self._read_entries(shop_id, batch_id=batch_id))
        return TransactionBatch(**dict(row), entries=entries)

    def create_ledger_entry(
        self,
        shop_id: int,
        batch_id: str,
        entry: LedgerEntryDraft,
        *,
        original_transcript: str | None = None,
        detected_language: str | None = None,
    ) -> LedgerEntry:
        return self.create_transaction_batch(
            shop_id, batch_id, (entry,),
            original_transcript=original_transcript,
            detected_language=detected_language,
        ).entries[0]

    def create_transaction_batch(
        self,
        shop_id: int,
        batch_id: str,
        entries: Sequence[LedgerEntryDraft],
        *,
        original_transcript: str | None = None,
        detected_language: str | None = None,
    ) -> TransactionBatch:
        validate_id(shop_id, "shop_id")
        if (
            not isinstance(batch_id, str) or not 1 <= len(batch_id) <= 128
            or batch_id != batch_id.strip() or "\x00" in batch_id
        ):
            raise ValueError("batch_id must contain 1–128 characters without surrounding whitespace")
        drafts = tuple(entries)
        if not drafts or not all(isinstance(entry, LedgerEntryDraft) for entry in drafts):
            raise ValueError("A batch requires at least one valid ledger entry")
        if original_transcript is not None and not isinstance(original_transcript, str):
            raise ValueError("original_transcript must be text")
        if detected_language is not None and (
            not isinstance(detected_language, str) or not detected_language.strip()
            or len(detected_language) > 64 or "\x00" in detected_language
        ):
            raise ValueError("detected_language must contain 1–64 characters and cannot be blank")

        self._require_shop(shop_id)
        existing = self.get_batch(shop_id, batch_id)
        if existing is not None:
            recorded_drafts = tuple(entry.as_draft() for entry in existing.entries)
            if (original_transcript, detected_language, drafts) != (
                existing.original_transcript, existing.detected_language, recorded_drafts,
            ):
                raise BatchConflict("Batch ID is already used for a different transaction")
            return existing

        # Keep the batch atomic even if a caller handles its error and continues the session.
        self.connection.execute("SAVEPOINT create_batch")
        try:
            self.connection.execute(
                """
                INSERT INTO transaction_batches (shop_id, id, original_transcript, detected_language)
                VALUES (?, ?, ?, ?)
                """,
                (shop_id, batch_id, original_transcript, detected_language),
            )
            for entry in drafts:
                self._insert_entry(shop_id, batch_id, entry)
            batch = self.get_batch(shop_id, batch_id)
            assert batch is not None
        except BaseException:
            if self.connection.in_transaction:
                self.connection.execute("ROLLBACK TO create_batch")
                self.connection.execute("RELEASE create_batch")
            raise
        self.connection.execute("RELEASE create_batch")
        return batch

    def _insert_entry(self, shop_id: int, batch_id: str, entry: LedgerEntryDraft) -> None:
        self._require_customer(shop_id, entry.customer_id)
        if entry.corrects_entry_id is not None:
            original = self.connection.execute(
                "SELECT 1 FROM ledger_entries WHERE shop_id = ? AND customer_id = ? AND id = ?",
                (shop_id, entry.customer_id, entry.corrects_entry_id),
            ).fetchone()
            if original is None:
                raise ValueError("Correction must reference an existing entry for the same customer")
        self.connection.execute(
            """
            INSERT INTO ledger_entries (
                shop_id, batch_id, customer_id, type, amount_paise, corrects_entry_id, payment_method
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (shop_id, batch_id, entry.customer_id, entry.type, entry.amount_paise,
             entry.corrects_entry_id, entry.payment_method),
        )

    def _require_shop(self, shop_id: int) -> None:
        if self.connection.execute("SELECT 1 FROM shops WHERE id = ?", (shop_id,)).fetchone() is None:
            raise ValueError("Shop not found")

    def _require_customer(self, shop_id: int, customer_id: int) -> None:
        if self.connection.execute(
            "SELECT 1 FROM customers WHERE shop_id = ? AND id = ?", (shop_id, customer_id),
        ).fetchone() is None:
            raise CustomerNotFound("Customer not found")

    def _read_entries(
        self, shop_id: int, *, customer_id: int | None = None, batch_id: str | None = None,
    ) -> list[LedgerEntry]:
        rows = self.connection.execute(
            """
            SELECT entry.*, batch.original_transcript, batch.detected_language
            FROM ledger_entries AS entry
            JOIN transaction_batches AS batch ON batch.shop_id = entry.shop_id AND batch.id = entry.batch_id
            WHERE entry.shop_id = ? AND (
                (? IS NOT NULL AND entry.customer_id = ?) OR (? IS NOT NULL AND entry.batch_id = ?)
            )
            ORDER BY entry.id
            """,
            (shop_id, customer_id, customer_id, batch_id, batch_id),
        )
        return [LedgerEntry(**dict(row)) for row in rows]

    def _read_customers(self, shop_id: int, customer_id: int | None = None) -> Iterator[Customer]:
        rows = self.connection.execute(
            """
            SELECT customer.id, customer.shop_id, customer.name, customer.created_at,
                   entry.balance_effect_paise, entry.created_at AS last_transaction_at
            FROM customers AS customer
            LEFT JOIN ledger_entries AS entry ON entry.shop_id = customer.shop_id AND entry.customer_id = customer.id
            WHERE customer.shop_id = ? AND (? IS NULL OR customer.id = ?)
            ORDER BY customer.id, entry.id
            """,
            (shop_id, customer_id, customer_id),
        )
        for _, group in groupby(rows, key=lambda row: row["id"]):
            first = next(group)
            customer = dict(first)
            del customer["balance_effect_paise"]
            # Python integers keep the sum exact even beyond SQLite's 64-bit SUM range.
            balance = 0
            for entry in chain((first,), group):
                balance += entry["balance_effect_paise"] or 0
                customer["last_transaction_at"] = entry["last_transaction_at"]
            yield Customer(**customer, balance_paise=balance)
