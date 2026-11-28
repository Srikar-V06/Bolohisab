import json
import sqlite3
from base64 import b64decode, urlsafe_b64encode
from dataclasses import dataclass, replace
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, ConfigDict, field_validator

from .auth import Authenticated, OwnedShop
from .auth_store import Account, linked_customer_scopes, normalize_phone
from .ledger import (
    MAX_SQLITE_INTEGER,
    Customer,
    CustomerNotFound,
    LedgerEntry,
    LedgerHistoryCursor,
    LedgerHistoryItem,
    ledger_session,
    validate_customer_name,
    validate_id,
)

router = APIRouter(prefix="/api/customers", tags=["customers"])
CustomerId = Annotated[int, Path(ge=1, le=MAX_SQLITE_INTEGER)]


class CustomerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    phone_number: str | None = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        return normalize_phone(value) if value is not None else None

    @field_validator("name")
    @classmethod
    def validate_name(cls, name: str) -> str:
        return validate_customer_name(name)


@dataclass(frozen=True)
class LedgerPage:
    items: list[LedgerHistoryItem]
    next_cursor: str | None
    has_more: bool


def _encode_cursor(customer_id: int, cursor: LedgerHistoryCursor) -> str:
    value = json.dumps([customer_id, cursor.created_at, cursor.entry_id, cursor.snapshot_id], separators=(",", ":"))
    return urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _decode_cursor(token: str, customer_id: int) -> LedgerHistoryCursor:
    try:
        value = b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True)
        owner, created_at, entry_id, snapshot_id = json.loads(value)
        validate_id(owner, "cursor owner")
        validate_id(entry_id, "cursor entry")
        validate_id(snapshot_id, "cursor snapshot")
        if owner != customer_id or entry_id > snapshot_id or not isinstance(created_at, str) or not created_at:
            raise ValueError()
        return LedgerHistoryCursor(created_at, entry_id, snapshot_id)
    except (TypeError, ValueError) as error:
        raise HTTPException(422, "Invalid ledger cursor") from error


@router.get("")
def list_customers(request: Request, session: Authenticated) -> list[Customer]:
    with ledger_session(request.app.state.database_path) as ledger:
        account = session.account
        if account.shop_id is not None:
            return ledger.list_customers(account.shop_id)
        return [ledger.get_customer(shop_id, customer_id)
                for shop_id, customer_id in linked_customer_scopes(ledger.connection, account.id)]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_customer(customer: CustomerCreate, request: Request, shop_id: OwnedShop) -> Customer:
    with ledger_session(request.app.state.database_path, write=True) as ledger:
        record = ledger.create_customer(shop_id, customer.name)
        if customer.phone_number is not None:
            ledger.connection.execute("UPDATE customers SET normalized_phone_number=? WHERE id=?",
                                      (customer.phone_number, record.id))
        return record


def _authorized_customer_shop(db: sqlite3.Connection, account: Account, customer_id: int) -> int:
    if account.shop_id is not None:
        return account.shop_id
    shop = db.execute(
        """
        SELECT c.shop_id FROM customer_account_links AS link JOIN customers AS c ON c.id = link.customer_id
        WHERE link.user_id = ? AND c.id = ?
        """,
        (account.id, customer_id),
    ).fetchone()
    if shop is None:
        raise HTTPException(404, "Customer not found")
    return shop["shop_id"]


@router.get("/{customer_id}")
def get_customer(customer_id: CustomerId, request: Request, session: Authenticated) -> Customer:
    with ledger_session(request.app.state.database_path) as ledger:
        try:
            shop_id = _authorized_customer_shop(ledger.connection, session.account, customer_id)
            return ledger.get_customer(shop_id, customer_id)
        except CustomerNotFound as error:
            raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/{customer_id}/ledger")
def get_customer_ledger(
    customer_id: CustomerId,
    request: Request,
    session: Authenticated,
    limit: Annotated[int | None, Query(ge=1, le=50)] = None,
    cursor: Annotated[str | None, Query(min_length=1, max_length=256)] = None,
) -> list[LedgerEntry] | LedgerPage:
    with ledger_session(request.app.state.database_path) as ledger:
        try:
            account = session.account
            shop_id = _authorized_customer_shop(ledger.connection, account, customer_id)
            if limit is None and cursor is None:
                entries = ledger.get_transaction_history(shop_id, customer_id)
                if account.role == "CUSTOMER":
                    return [replace(entry, original_transcript=None, detected_language=None) for entry in entries]
                return entries
            position = _decode_cursor(cursor, customer_id) if cursor is not None else None
            items, following = ledger.get_transaction_history_page(shop_id, customer_id, limit or 5, position)
        except CustomerNotFound as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if account.role == "CUSTOMER":
            # A single shopkeeper voice transcript can mention other people in the same batch.
            items = [replace(entry, original_transcript=None, detected_language=None) for entry in items]
        return LedgerPage(items, _encode_cursor(customer_id, following) if following else None, following is not None)
