from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from .auth import OwnedShop
from .language_detector import TranscriptLanguage, detect_language
from .ledger import MAX_SQLITE_INTEGER, ledger_session
from .parser import ClarificationRequired, ReportIntent, parse_report
from .public_receipt import INDIA

router = APIRouter(prefix="/api/voice", tags=["voice reports"])


class ReportQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transcript: Annotated[str, Field(min_length=1, max_length=2000)]
    language: TranscriptLanguage
    store_id: Annotated[StrictInt, Field(ge=1, le=MAX_SQLITE_INTEGER)]


def money(paise):
    rupees, fraction = divmod(abs(paise), 100)
    return f"{'-' if paise < 0 else ''}₹{rupees}.{fraction:02d}"


def daily_report(db, shop, intent, now, english):
    start = datetime.fromtimestamp(now, INDIA).replace(hour=0, minute=0, second=0, microsecond=0)
    bounds = [dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
              for dt in (start, start + timedelta(days=1))]
    params = {"date": start.date().isoformat(), "timezone": "Asia/Kolkata"}
    scope = "FROM ledger_entries WHERE shop_id=? AND created_at>=? AND created_at<?"
    if intent == ReportIntent.TRANSACTION_COUNT:
        count = db.execute("SELECT count(*) " + scope, (shop, *bounds)).fetchone()[0]
        return params, {"count": count}, (f"{count} transactions today." if english else f"आज {count} लेनदेन हुए।")
    collections = intent == ReportIntent.COLLECTIONS
    rows = db.execute("SELECT amount_paise " + scope + " AND type=?", (shop, *bounds, "PAYMENT" if collections else "CREDIT"))
    amount = sum(row[0] for row in rows)
    if collections:
        text = f"Collected {money(amount)} today." if english else f"आज {money(amount)} प्राप्त हुए।"
    else:
        text = f"Gave {money(amount)} in credit today." if english else f"आज {money(amount)} उधार दिया।"
    return params, {"amount_paise": amount}, text


@router.post("/query")
def query(payload: ReportQuery, request: Request, shop: OwnedShop):
    if payload.store_id != shop:
        raise HTTPException(404, "STORE_NOT_FOUND")
    detected = detect_language(payload.transcript)
    english = payload.language == TranscriptLanguage.ENGLISH
    with ledger_session(request.app.state.database_path) as ledger:
        try:
            intent, customer = parse_report(payload.transcript, ledger.list_customer_names(shop))
        except ClarificationRequired as error:
            raise HTTPException(422, {"code": error.code, "candidates": [asdict(c) for c in error.candidates]}) from error
        params = {}
        if intent == ReportIntent.CUSTOMER_BALANCE:
            amount = ledger.calculate_balance(shop, customer.id)
            params = {"customer_id": customer.id}
            result = {"customer_id": customer.id, "customer_name": customer.name, "balance_paise": amount}
            text = (f"{customer.name}'s balance is {money(amount)}." if english
                    else f"{customer.name} का शेष {money(amount)} है।")
        elif intent == ReportIntent.TOP_OUTSTANDING:
            customers = ledger.list_customers(shop)
            highest = max((c.balance_paise for c in customers), default=0)
            leaders = [{"customer_id": c.id, "customer_name": c.name} for c in customers if c.balance_paise == highest > 0]
            result = {"customers": leaders, "balance_paise": max(0, highest)}
            names = ", ".join(c["customer_name"] for c in leaders)
            if leaders:
                text = (f"Highest outstanding balance is {money(highest)} for {names}." if english
                        else f"सबसे अधिक बकाया {names} का है, {money(highest)}।")
            else:
                text = "No outstanding balances." if english else "कोई बकाया नहीं है।"
        else:
            params, result, text = daily_report(ledger.connection, shop, intent, request.app.state.auth_clock(), english)
    return {"detected_language": detected, "intent": intent, "structured_parameters": params,
            "result": result, "localized_text": text, "speech_text": text}
