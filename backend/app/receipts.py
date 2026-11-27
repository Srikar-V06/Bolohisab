from datetime import datetime, timedelta, timezone
from html import escape
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict

from .customers import CustomerId
from .database import DEFAULT_SHOP_ID, database_transaction
from .localization import LanguageCode
from .receipt_store import (
    ReceiptItem, ReceiptNotFound, generate_receipt, get_shared_receipt, list_receipt_items,
    mark_receipt_sent,
)

router = APIRouter(prefix="/api/receipts", tags=["receipts"])


class ReceiptLanguage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: LanguageCode


@router.get("")
def receipts(request: Request) -> list[ReceiptItem]:
    with database_transaction(request.app.state.database_path) as connection:
        return list_receipt_items(connection, DEFAULT_SHOP_ID)


@router.post("/{entry_id}")
def issue(entry_id: CustomerId, payload: ReceiptLanguage, request: Request) -> ReceiptItem:
    with database_transaction(request.app.state.database_path, write=True) as connection:
        try:
            return generate_receipt(connection, DEFAULT_SHOP_ID, entry_id, payload.language)
        except ReceiptNotFound as error:
            raise HTTPException(404, "ENTRY_NOT_FOUND") from error


@router.post("/{entry_id}/sent")
def sent(entry_id: CustomerId, request: Request) -> ReceiptItem:
    with database_transaction(request.app.state.database_path, write=True) as connection:
        try:
            return mark_receipt_sent(connection, DEFAULT_SHOP_ID, entry_id)
        except ReceiptNotFound as error:
            raise HTTPException(404, "RECEIPT_NOT_FOUND") from error


def _money(paise: int) -> str:
    whole, fraction = divmod(abs(paise), 100)
    amount = f"{whole}.{fraction:02d}" if fraction else str(whole)
    return ("−" if paise < 0 else "") + "₹" + amount


@router.get("/share/{token}", response_class=HTMLResponse)
def shared(
    token: Annotated[str, Path(min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]+$")],
    request: Request,
    language: LanguageCode | None = None,
) -> HTMLResponse:
    with database_transaction(request.app.state.database_path) as connection:
        try:
            item = get_shared_receipt(connection, token)
        except ReceiptNotFound as error:
            raise HTTPException(404, "RECEIPT_NOT_FOUND") from error

    locale = language or item.language or LanguageCode.HINDI
    if locale == LanguageCode.HINDI:
        title = "रसीद"
        labels = ("ग्राहक", "लेन-देन आईडी", "तारीख़ और समय", "लेन-देन", "रकम", "लेन-देन के बाद बकाया")
        kind = {"CREDIT": "उधार", "PAYMENT": "भुगतान", "ADJUSTMENT": "समायोजन"}[item.type]
        method = {"CASH": "नकद", "UPI": "UPI"}.get(item.payment_method)
    else:
        title = "Receipt"
        labels = ("Customer", "Transaction ID", "Date and time", "Transaction", "Amount", "Balance after transaction")
        kind = {"CREDIT": "Credit", "PAYMENT": "Payment", "ADJUSTMENT": "Adjustment"}[item.type]
        method = {"CASH": "Cash", "UPI": "UPI"}.get(item.payment_method)
    if method:
        kind = f"{kind} · {method}"
    date = datetime.fromisoformat(item.created_at).astimezone(timezone(timedelta(hours=5, minutes=30), "IST"))
    values = (item.customer_name, str(item.entry_id), date.strftime("%d/%m/%Y %H:%M IST"), kind,
              _money(item.amount_paise), _money(item.balance_after_paise))
    rows = "".join(f"<dt>{label}</dt><dd>{escape(value)}</dd>" for label, value in zip(labels, values, strict=True))
    return HTMLResponse(
        f"""<!doctype html><html lang="{locale}"><meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <title>{title} · BoloHisaab</title>
        <style>body{{margin:0;padding:1rem;background:#f7f8f5;color:#17231c;font:1rem/1.6 system-ui,sans-serif}}
        main{{max-width:26rem;margin:2rem auto;padding:1.5rem;background:#fff;border:1px solid #e4e9e4;border-radius:1rem}}
        h1,dt{{color:#176b4d}}dt{{font-weight:600}}dd{{margin:0 0 .8rem;overflow-wrap:anywhere}}</style>
        <main><h1>{title}</h1><p>{escape(item.shop_name)}</p><dl>{rows}</dl></main></html>""",
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex"},
    )
