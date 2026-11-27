from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Request, status
from pydantic import BaseModel, ConfigDict, field_validator

from .database import DEFAULT_SHOP_ID
from .ledger import (
    MAX_SQLITE_INTEGER,
    Customer,
    CustomerNotFound,
    LedgerEntry,
    ledger_session,
    validate_customer_name,
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
def get_customer_ledger(customer_id: CustomerId, request: Request) -> list[LedgerEntry]:
    with ledger_session(request.app.state.database_path) as ledger:
        try:
            return ledger.get_transaction_history(DEFAULT_SHOP_ID, customer_id)
        except CustomerNotFound as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
