from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from .auth import CustomerAccount
from .auth_store import linked_customer_scopes
from .customers import CustomerId, LedgerPage, _decode_cursor, _encode_cursor
from .database import database_transaction
from .ledger import Ledger, MAX_SQLITE_INTEGER
from .receipts import customer_receipt_items

router = APIRouter(prefix="/api/customer", tags=["customer portal"])
Limit = Annotated[int, Query(ge=1, le=50)]


def linked_record(db, account, store):
    rows = db.execute("SELECT store_customer_id FROM store_customer_links WHERE customer_user_id=? "
                      "AND store_id=? AND status='ACTIVE'", (account, store)).fetchall()
    if not rows:
        raise HTTPException(404, "STORE_NOT_FOUND")
    if len(rows) > 1:
        raise HTTPException(409, "MULTIPLE_LEDGER_RECORDS")
    return rows[0][0]


def store_summary(db, user, shop, customer):
    record = Ledger(db).get_customer(shop, customer)
    info = db.execute("SELECT name,address FROM shops WHERE id=?", (shop,)).fetchone()
    unread = db.execute("SELECT count(*) FROM notifications WHERE customer_user_id=? AND store_id=? "
                        "AND store_customer_id=? AND read_at IS NULL", (user, shop, customer)).fetchone()[0]
    return {"store_id": shop, "store_name": info["name"], "store_information": {"address": info["address"]},
            "outstanding_balance_paise": record.balance_paise, "last_transaction_at": record.last_transaction_at,
            "unread_notification_count": unread}


@router.get("/stores")
def stores(request: Request, account: CustomerAccount):
    with database_transaction(request.app.state.database_path) as db:
        return [store_summary(db, account.id, shop, customer)
                for shop, customer in linked_customer_scopes(db, account.id)]


@router.get("/stores/{store_id}")
def store(store_id: CustomerId, request: Request, account: CustomerAccount):
    with database_transaction(request.app.state.database_path) as db:
        return store_summary(db, account.id, store_id, linked_record(db, account.id, store_id))


@router.get("/stores/{store_id}/ledger")
def ledger(store_id: CustomerId, request: Request, account: CustomerAccount, limit: Limit = 5,
           cursor: Annotated[str | None, Query(min_length=1, max_length=256)] = None) -> LedgerPage:
    with database_transaction(request.app.state.database_path) as db:
        customer = linked_record(db, account.id, store_id)
        position = _decode_cursor(cursor, customer) if cursor else None
        try:
            items, following = Ledger(db).get_transaction_history_page(store_id, customer, limit, position)
        except ValueError as error:
            raise HTTPException(422, "INVALID_CURSOR") from error
        items = [replace(item, original_transcript=None, detected_language=None) for item in items]
        return LedgerPage(items, _encode_cursor(customer, following) if following else None, following is not None)


@router.get("/stores/{store_id}/receipts")
def receipts(store_id: CustomerId, request: Request, account: CustomerAccount):
    with database_transaction(request.app.state.database_path) as db:
        customer = linked_record(db, account.id, store_id)
        return sorted(customer_receipt_items(db, store_id, customer), key=lambda item: item["entry_id"], reverse=True)


# Apply identical live-link visibility to the feed, counters and read operations.
VISIBLE = """customer_user_id=? AND EXISTS (
    SELECT 1 FROM store_customer_links l WHERE l.customer_user_id=notifications.customer_user_id
    AND l.store_id=notifications.store_id AND l.store_customer_id=notifications.store_customer_id
    AND l.status='ACTIVE')"""


@router.get("/notifications")
def notifications(request: Request, account: CustomerAccount, limit: Limit = 5,
                  cursor: Annotated[int | None, Query(ge=1, le=MAX_SQLITE_INTEGER)] = None):
    with database_transaction(request.app.state.database_path) as db:
        rows = db.execute(f"""
            SELECT notifications.id,store_id,s.name AS store_name,receipt_id,e.amount_paise,
                   notifications.created_at,read_at,notification_type
            FROM notifications JOIN shops s ON s.id=store_id JOIN receipts r ON r.id=receipt_id
            JOIN ledger_entries e ON e.id=r.ledger_entry_id
            WHERE {VISIBLE} AND (? IS NULL OR notifications.id<?)
            ORDER BY notifications.id DESC LIMIT ?
        """, (account.id, cursor, cursor, limit+1)).fetchall()
        more = len(rows) > limit
        return {"items": [dict(row) for row in rows[:limit]], "has_more": more,
                "next_cursor": str(rows[limit-1]["id"]) if more else None}


@router.get("/notifications/unread-count")
def unread(request: Request, account: CustomerAccount):
    with database_transaction(request.app.state.database_path) as db:
        count = db.execute(f"SELECT count(*) FROM notifications WHERE {VISIBLE} AND read_at IS NULL",
                           (account.id,)).fetchone()[0]
        return {"unread_count": count}


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: CustomerId, request: Request, account: CustomerAccount):
    with database_transaction(request.app.state.database_path, write=True) as db:
        row = db.execute(f"""UPDATE notifications SET read_at=coalesce(read_at,strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                            WHERE {VISIBLE} AND id=? RETURNING id,read_at""", (account.id, notification_id)).fetchone()
        if not row:
            raise HTTPException(404, "NOTIFICATION_NOT_FOUND")
        return dict(row)


@router.post("/notifications/read-all")
def read_all(request: Request, account: CustomerAccount):
    with database_transaction(request.app.state.database_path, write=True) as db:
        updated = db.execute(f"""UPDATE notifications SET read_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                                WHERE {VISIBLE} AND read_at IS NULL""", (account.id,)).rowcount
        return {"updated_count": updated}
