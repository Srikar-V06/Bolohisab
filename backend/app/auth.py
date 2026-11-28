import sqlite3
from dataclasses import dataclass
from ipaddress import ip_address
from os import environ
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints, field_validator

from .auth_store import (
    SESSION_IDLE_TIMEOUT, SESSION_LIFETIME, Account, Role, create_account, csrf_token, digest,
    hash_password, new_session, normalize_phone, read_account, reserve_attempt, revoke_session,
    session_token, verify_csrf, verify_password,
)
from .database import database_transaction


COOKIE = "bolo_session"
MUTATIONS = {"POST", "PUT", "PATCH", "DELETE"}
router = APIRouter(prefix="/api/auth", tags=["authentication"])
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


@dataclass(frozen=True)
class AuthConfig:
    secure_cookie: bool
    origins: tuple[str, ...]
    trust_proxy: bool


def auth_config() -> AuthConfig:
    environment = environ.get("BOLO_ENV", "development")
    if environment not in ("development", "production"):
        raise ValueError("BOLO_ENV must be development or production")
    secure = environment == "production"
    default_origins = "" if secure else ",".join(
        f"http://{host}:{port}" for host in ("localhost", "127.0.0.1") for port in (3000, 5173)
    )
    origins = tuple(origin.strip() for origin in environ.get("BOLO_ALLOWED_ORIGINS", default_origins).split(",")
                    if origin.strip())
    for origin in origins:
        url = urlsplit(origin)
        if (url.scheme not in ("http", "https") or not url.hostname or url.username is not None
            or url.path or url.query or url.fragment or "*" in origin
            or (url.scheme == "http" and (secure or url.hostname not in ("localhost", "127.0.0.1", "::1")))):
            raise ValueError("BOLO_ALLOWED_ORIGINS requires explicit HTTPS origins or local development origins")
    return AuthConfig(secure, origins, environ.get("BOLO_AUTH_TRUST_PROXY") == "1")


def validate_origin(request: Request, *, public_receipt: bool = False) -> None:
    origin = request.headers.get("origin")
    if origin is None:
        return
    origins = request.app.state.auth_config.origins
    if public_receipt:
        origins = (*origins, request.app.state.public_receipt_origin)
        if not request.app.state.auth_config.secure_cookie:
            origins += ("http://127.0.0.1:3011", "http://localhost:3011")
    if not origin or origin not in origins:
        raise HTTPException(403, "ORIGIN_NOT_ALLOWED")


def _attempt(request: Request, purpose: str, phone: str) -> None:
    validate_origin(request)
    if request.headers.get("content-type", "").split(";", 1)[0].lower().strip() != "application/json":
        raise HTTPException(415, "JSON_REQUIRED")
    peer = request.client.host if request.client else "unknown"
    if request.app.state.auth_config.trust_proxy:
        try:
            peer = str(ip_address(request.headers.get("x-bolo-client-ip", "")))
        except ValueError:
            pass
    with database_transaction(request.app.state.database_path, write=True) as db:
        wait = reserve_attempt(db, purpose, phone, peer, request.app.state.auth_clock())
    if wait:
        raise HTTPException(429, "AUTH_RATE_LIMITED", headers={"Retry-After": str(wait)})


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    phone_number: str = Field(min_length=1, max_length=48)
    password: SecretStr = Field(min_length=1, max_length=1024)

    @field_validator("phone_number")
    @classmethod
    def phone(cls, value: str) -> str:
        return normalize_phone(value)


class Registration(Credentials):
    full_name: Name
    password: SecretStr = Field(min_length=10, max_length=1024)


class ShopRegistration(Registration):
    shop_name: Name
    shop_address: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class Login(Credentials):
    role: Role | None = None


@dataclass(frozen=True)
class Session:
    account: Account
    token_hash: str
    csrf: str


def require_authenticated_user(request: Request, response: Response) -> Session:
    mutation = request.method in MUTATIONS
    if mutation:
        validate_origin(request)
    raw = session_token(request.cookies.get(COOKIE))
    if raw is None:
        raise HTTPException(401, "AUTH_REQUIRED")
    token_hash = digest(raw)
    now = request.app.state.auth_clock()
    with database_transaction(request.app.state.database_path, write=True) as db:
        row = db.execute(
            """
            SELECT users.*, auth_sessions.csrf_nonce, auth_sessions.csrf_hash
            FROM auth_sessions JOIN users ON users.id = auth_sessions.user_id
            WHERE token_hash = ? AND revoked_at IS NULL AND expires_at > ?
              AND last_activity_at > ? AND users.is_active = 1
            """,
            (token_hash, now, now - SESSION_IDLE_TIMEOUT),
        ).fetchone()
        if row is None:
            raise HTTPException(401, "AUTH_REQUIRED")
        if mutation and not verify_csrf(request.headers.get("x-csrf-token"), row["csrf_hash"]):
            raise HTTPException(403, "CSRF_INVALID")
        db.execute("UPDATE auth_sessions SET last_activity_at = max(last_activity_at, ?) WHERE token_hash = ?",
                   (now, token_hash))
        response.headers["Cache-Control"] = "no-store"
        return Session(read_account(row), token_hash, csrf_token(raw, row["csrf_nonce"]))


Authenticated = Annotated[Session, Depends(require_authenticated_user)]


def require_shopkeeper(session: Authenticated) -> Account:
    if session.account.role != "SHOPKEEPER":
        raise HTTPException(403, "ROLE_FORBIDDEN")
    return session.account


def require_customer(session: Authenticated) -> Account:
    if session.account.role != "CUSTOMER":
        raise HTTPException(403, "ROLE_FORBIDDEN")
    return session.account


Shopkeeper = Annotated[Account, Depends(require_shopkeeper)]


def require_store_owner(account: Shopkeeper) -> int:
    # Shop is taken from the authenticated account, never from a request parameter.
    assert account.shop_id is not None
    return account.shop_id


OwnedShop = Annotated[int, Depends(require_store_owner)]


def _register(request: Request, payload: Registration, role: Role) -> Account:
    _attempt(request, "register", payload.phone_number)
    encoded = hash_password(payload.password.get_secret_value())
    try:
        with database_transaction(request.app.state.database_path, write=True) as db:
            shop_id = None
            if isinstance(payload, ShopRegistration):
                shop_id = db.execute(
                    "INSERT INTO shops (name, address) VALUES (?, ?) RETURNING id",
                    (payload.shop_name, payload.shop_address or None),
                ).fetchone()["id"]
            return create_account(db, payload.full_name, payload.phone_number, encoded, role, shop_id)
    except sqlite3.IntegrityError:
        raise HTTPException(409, "REGISTRATION_FAILED") from None


@router.post("/register/shopkeeper", status_code=201)
def register_shopkeeper(payload: ShopRegistration, request: Request) -> Account:
    return _register(request, payload, "SHOPKEEPER")


@router.post("/register/customer", status_code=201)
def register_customer(payload: Registration, request: Request) -> Account:
    return _register(request, payload, "CUSTOMER")


@router.post("/login")
def login(payload: Login, request: Request, response: Response) -> Account:
    _attempt(request, "login", payload.phone_number)
    with database_transaction(request.app.state.database_path) as db:
        row = db.execute("SELECT * FROM users WHERE normalized_phone_number = ?", (payload.phone_number,)).fetchone()
    if (
        not verify_password(row["password_hash"] if row else None, payload.password.get_secret_value())
        or row is None or not row["is_active"] or (payload.role is not None and payload.role != row["role"])
    ):
        raise HTTPException(401, "INVALID_CREDENTIALS")
    with database_transaction(request.app.state.database_path, write=True) as db:
        current = db.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()
        if current is None or not current["is_active"] or current["password_hash"] != row["password_hash"]:
            raise HTTPException(401, "INVALID_CREDENTIALS")
        raw = new_session(db, current["id"], request.app.state.auth_clock(), session_token(request.cookies.get(COOKIE)))
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(COOKIE, raw, max_age=SESSION_LIFETIME, httponly=True,
                        secure=request.app.state.auth_config.secure_cookie, samesite="lax", path="/")
    return read_account(current)


@router.get("/me")
def me(session: Authenticated, response: Response) -> Account:
    response.headers["Cache-Control"] = "no-store"
    return session.account


@router.get("/csrf")
def csrf(session: Authenticated, response: Response) -> dict[str, str]:
    response.headers["Cache-Control"] = "no-store"
    return {"csrf_token": session.csrf}


@router.post("/logout", status_code=204, response_class=Response)
def logout(request: Request, session: Authenticated) -> Response:
    with database_transaction(request.app.state.database_path, write=True) as db:
        revoke_session(db, session.token_hash, request.app.state.auth_clock())
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    response.delete_cookie(COOKIE, secure=request.app.state.auth_config.secure_cookie, httponly=True, samesite="lax")
    return response
