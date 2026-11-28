from datetime import UTC, datetime
from secrets import token_urlsafe

from fastapi import APIRouter, HTTPException, Request

from .auth import CustomerAccount, OwnedShop
from .auth_store import digest, session_token
from .customers import CustomerId
from .database import database_transaction

router = APIRouter(prefix="/api", tags=["customer invitations"])
CUSTOMER_PATH = "/shopkeeper/customers/{customer_id}"
INVITATION_PATH = "/customer-invitations/{token}"


def expiry_text(epoch):
    return datetime.fromtimestamp(epoch, UTC).isoformat().replace("+00:00", "Z")


def require_record(db, shop, customer):
    if not db.execute("SELECT 1 FROM customers WHERE shop_id=? AND id=?", (shop, customer)).fetchone():
        raise HTTPException(404, "CUSTOMER_NOT_FOUND")


def link_status(db, shop, customer, now):
    require_record(db, shop, customer)
    link = db.execute("SELECT linked_at FROM store_customer_links WHERE store_id=? AND store_customer_id=? "
                      "AND status='ACTIVE'", (shop, customer)).fetchone()
    invite = db.execute("SELECT status, expires_at FROM customer_invitations WHERE store_customer_id=? "
                        "ORDER BY id DESC LIMIT 1", (customer,)).fetchone()
    status = invite["status"] if invite else None
    if status == "PENDING" and invite["expires_at"] <= now:
        status = "EXPIRED"
    return {"linked": bool(link), "linked_at": link["linked_at"] if link else None,
            "invitation_status": status, "invitation_expiry": expiry_text(invite["expires_at"]) if invite else None}


@router.get(CUSTOMER_PATH + "/link-status")
def get_link_status(customer_id: CustomerId, request: Request, shop: OwnedShop):
    with database_transaction(request.app.state.database_path) as db:
        return link_status(db, shop, customer_id, request.app.state.auth_clock())


@router.post(CUSTOMER_PATH + "/invite", status_code=201)
def invite(customer_id: CustomerId, request: Request, shop: OwnedShop):
    with database_transaction(request.app.state.database_path, write=True) as db:
        now = request.app.state.auth_clock()
        status = link_status(db, shop, customer_id, now)
        if status["linked"]:
            raise HTTPException(409, "CUSTOMER_ALREADY_LINKED")
        if status["invitation_status"] == "PENDING":
            raise HTTPException(409, "INVITATION_PENDING")
        db.execute("UPDATE customer_invitations SET status='EXPIRED' WHERE store_customer_id=? AND status='PENDING'",
                   (customer_id,))
        token = token_urlsafe(32)
        expiry = now + 7 * 86400
        db.execute("INSERT INTO customer_invitations(store_id,store_customer_id,token_hash,expires_at,status) "
                   "VALUES(?,?,?,?,'PENDING')", (shop, customer_id, digest(token), expiry))
        origins = request.app.state.auth_config.origins
        origin = origins[0] if origins else ""
        return {"invitation_url": f"{origin}/api/customer-invitations/{token}", "expires_at": expiry_text(expiry)}


@router.delete(CUSTOMER_PATH + "/invite")
def revoke_invitation(customer_id: CustomerId, request: Request, shop: OwnedShop):
    with database_transaction(request.app.state.database_path, write=True) as db:
        require_record(db, shop, customer_id)
        now = request.app.state.auth_clock()
        db.execute("UPDATE customer_invitations SET status=CASE WHEN expires_at<=? THEN 'EXPIRED' ELSE 'REVOKED' END "
                   "WHERE store_customer_id=? AND status='PENDING'", (now, customer_id))
        return link_status(db, shop, customer_id, now)


@router.delete(CUSTOMER_PATH + "/link")
def revoke_link(customer_id: CustomerId, request: Request, shop: OwnedShop):
    with database_transaction(request.app.state.database_path, write=True) as db:
        require_record(db, shop, customer_id)
        db.execute("UPDATE store_customer_links SET status='REVOKED', revoked_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                   "WHERE store_id=? AND store_customer_id=? AND status='ACTIVE'", (shop, customer_id))
        return link_status(db, shop, customer_id, request.app.state.auth_clock())


def valid_invitation(db, token, account, now):
    row = db.execute("""
        SELECT i.*, s.name AS store_name, c.name AS customer_name, c.normalized_phone_number
        FROM customer_invitations i JOIN shops s ON s.id=i.store_id
        JOIN customers c ON c.shop_id=i.store_id AND c.id=i.store_customer_id
        WHERE i.token_hash=?
    """, (digest(token),)).fetchone() if session_token(token) else None
    if not row:
        raise HTTPException(404, "INVITATION_NOT_FOUND")
    if row["status"] == "CLAIMED":
        raise HTTPException(409, "INVITATION_CLAIMED")
    if row["status"] != "PENDING" or now >= row["expires_at"]:
        raise HTTPException(410, "INVITATION_INACTIVE")
    if row["normalized_phone_number"] and row["normalized_phone_number"] != account.normalized_phone_number:
        raise HTTPException(403, "PHONE_MISMATCH")
    return row


@router.get(INVITATION_PATH)
def preview(token: str, request: Request, account: CustomerAccount):
    with database_transaction(request.app.state.database_path) as db:
        row = valid_invitation(db, token, account, request.app.state.auth_clock())
        return {"store_id": row["store_id"], "store_name": row["store_name"], "customer_name": row["customer_name"],
                "expires_at": expiry_text(row["expires_at"])}


@router.post(INVITATION_PATH + "/claim")
def claim(token: str, request: Request, account: CustomerAccount):
    with database_transaction(request.app.state.database_path, write=True) as db:
        row = valid_invitation(db, token, account, request.app.state.auth_clock())
        if db.execute("SELECT 1 FROM store_customer_links WHERE status='ACTIVE' AND "
                      "(store_customer_id=? OR (store_id=? AND customer_user_id=?))",
                      (row["store_customer_id"], row["store_id"], account.id)).fetchone():
            raise HTTPException(409, "CUSTOMER_ALREADY_LINKED")
        link = db.execute("INSERT INTO store_customer_links(customer_user_id,store_id,store_customer_id) "
                          "VALUES(?,?,?) RETURNING store_id,store_customer_id,linked_at",
                          (account.id, row["store_id"], row["store_customer_id"])).fetchone()
        db.execute("UPDATE customer_invitations SET status='CLAIMED' WHERE id=?", (row["id"],))
        return dict(link)
