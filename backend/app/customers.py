import json
from base64 import b64decode, urlsafe_b64encode
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, ConfigDict, field_validator

from .database import DEFAULT_SHOP_ID
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
def list_customers(request: Request) -> list[Customer]:
    with ledger_session(request.app.state.database_path) as ledger:
        return ledger.list_customers(DEFAULT_SHOP_ID)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_customer(customer: CustomerCreate, request: Request) -> Customer:
    with ledger_session(request.app.state.database_path, write=True) as ledger:
        return ledger.create_customer(DEFAULT_SHOP_ID, customer.name)


@router.get("/{customer_id}")
def get_customer(customer_id: CustomerId, request: Request) -> Customer:
    with ledger_session(request.app.state.database_path) as ledger:
        try:
            return ledger.get_customer(DEFAULT_SHOP_ID, customer_id)
        except CustomerNotFound as error:
            raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/{customer_id}/ledger")
def get_customer_ledger(
    customer_id: CustomerId,
    request: Request,
    limit: Annotated[int | None, Query(ge=1, le=50)] = None,
    cursor: Annotated[str | None, Query(min_length=1, max_length=256)] = None,
) -> list[LedgerEntry] | LedgerPage:
    with ledger_session(request.app.state.database_path) as ledger:
        try:
            if limit is None and cursor is None:
                return ledger.get_transaction_history(DEFAULT_SHOP_ID, customer_id)
            position = _decode_cursor(cursor, customer_id) if cursor is not None else None
            items, following = ledger.get_transaction_history_page(DEFAULT_SHOP_ID, customer_id, limit or 5, position)
        except CustomerNotFound as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return LedgerPage(items, _encode_cursor(customer_id, following) if following else None, following is not None)
