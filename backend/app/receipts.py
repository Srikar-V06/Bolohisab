from dataclasses import asdict
from os import environ
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, StrictInt, StringConstraints

from .customers import CustomerId
from .database import DEFAULT_SHOP_ID, database_transaction
from .localization import LanguageCode
from .public_receipt import render_shared_receipt
from .receipt_store import (
    DisputeDecision, ReceiptConflict, ReceiptItem, ReceiptNotFound, confirm_shared_receipt,
    dispute_shared_receipt, generate_receipt, get_shared_receipt, list_receipt_items, mark_receipt_sent,
    review_receipt_dispute,
)

router = APIRouter(prefix="/api/receipts", tags=["receipts"])
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
PaiseText = Annotated[str, StringConstraints(pattern=r"^-?(0|[1-9][0-9]{0,18})$")]


class ReceiptLanguage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: LanguageCode


class DisputeClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claimed_amount_paise: StrictInt | PaiseText
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class DisputeReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: DisputeDecision
    reviewer: ShortText


def public_receipt_origin() -> str:
    origin = environ.get("PUBLIC_RECEIPT_ORIGIN", "").strip().rstrip("/")
    if not origin:
        return ""
    url = urlsplit(origin)
    if (url.scheme not in ("http", "https") or not url.hostname or url.username is not None
        or url.path or url.query or url.fragment
        or (url.scheme == "http" and url.hostname not in ("localhost", "127.0.0.1", "::1"))):
        raise ValueError("PUBLIC_RECEIPT_ORIGIN must be an HTTPS origin or a local HTTP origin")
    return origin


def _receipt_payload(item: ReceiptItem, origin: str) -> dict:
    data = asdict(item)
    data["share_url"] = f"{origin}/api/receipts/share/{item.share_token}" if origin and item.share_token else None
    for fields in (data, data["dispute"] or {}):
        for field, value in fields.items():
            # Keep the existing numeric API for safe values. A string carries larger paise exactly.
            if field.endswith("_paise") and abs(value) > 2**53 - 1:
                fields[field] = str(value)
    return data


@router.get("")
def receipts(request: Request) -> list[dict]:
    with database_transaction(request.app.state.database_path) as connection:
        return [_receipt_payload(item, request.app.state.public_receipt_origin)
                for item in list_receipt_items(connection, DEFAULT_SHOP_ID)]


@router.post("/{entry_id}")
def issue(entry_id: CustomerId, payload: ReceiptLanguage, request: Request) -> dict:
    with database_transaction(request.app.state.database_path, write=True) as connection:
        try:
            item = generate_receipt(connection, DEFAULT_SHOP_ID, entry_id, payload.language)
        except ReceiptNotFound as error:
            raise HTTPException(404, "ENTRY_NOT_FOUND") from error
        return _receipt_payload(item, request.app.state.public_receipt_origin)


@router.post("/{entry_id}/sent")
def sent(entry_id: CustomerId, request: Request) -> dict:
    with database_transaction(request.app.state.database_path, write=True) as connection:
        try:
            item = mark_receipt_sent(connection, DEFAULT_SHOP_ID, entry_id)
        except ReceiptNotFound as error:
            raise HTTPException(404, "RECEIPT_NOT_FOUND") from error
        return _receipt_payload(item, request.app.state.public_receipt_origin)


@router.post("/{entry_id}/dispute/review")
def review(entry_id: CustomerId, payload: DisputeReview, request: Request) -> dict:
    with database_transaction(request.app.state.database_path, write=True) as connection:
        try:
            item = review_receipt_dispute(connection, DEFAULT_SHOP_ID, entry_id, payload.decision, payload.reviewer)
        except ReceiptNotFound as error:
            raise HTTPException(404, "DISPUTE_NOT_FOUND") from error
        except ReceiptConflict as error:
            raise HTTPException(409, str(error)) from error
        return _receipt_payload(item, request.app.state.public_receipt_origin)


@router.get("/share/{token}", response_class=HTMLResponse)
def shared(token: str, request: Request, language: LanguageCode | None = None) -> HTMLResponse:
    with database_transaction(request.app.state.database_path) as connection:
        try:
            item = get_shared_receipt(connection, token)
        except ReceiptNotFound:
            item = None
    return render_shared_receipt(item, language)


@router.post("/share/{token}/confirm", status_code=204, response_class=Response)
def customer_confirm(token: str, request: Request) -> Response:
    with database_transaction(request.app.state.database_path, write=True) as connection:
        try:
            confirm_shared_receipt(connection, token)
        except ReceiptNotFound as error:
            raise HTTPException(404, "RECEIPT_NOT_FOUND") from error
        except ReceiptConflict as error:
            raise HTTPException(409, str(error)) from error
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post("/share/{token}/dispute", status_code=204, response_class=Response)
def customer_dispute(token: str, payload: DisputeClaim, request: Request) -> Response:
    with database_transaction(request.app.state.database_path, write=True) as connection:
        try:
            dispute_shared_receipt(connection, token, int(payload.claimed_amount_paise), payload.reason)
        except ReceiptNotFound as error:
            raise HTTPException(404, "RECEIPT_NOT_FOUND") from error
        except ReceiptConflict as error:
            raise HTTPException(422 if str(error) == "INVALID_CLAIM" else 409, str(error)) from error
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
