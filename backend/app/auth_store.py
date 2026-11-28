import sqlite3
from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest, digest as hmac_digest
from re import fullmatch, sub
from secrets import token_urlsafe
from typing import Literal

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


Role = Literal["SHOPKEEPER", "CUSTOMER"]
SESSION_LIFETIME = 7 * 24 * 60 * 60
SESSION_IDLE_TIMEOUT = 24 * 60 * 60
ATTEMPT_WINDOW = 15 * 60
_hasher = PasswordHasher(type=Type.ID)
_dummy_hash = _hasher.hash(token_urlsafe(32))


@dataclass(frozen=True)
class Account:
    id: int
    full_name: str
    normalized_phone_number: str
    role: Role
    shop_id: int | None
    is_active: bool
    created_at: str
    updated_at: str


def normalize_phone(value: str) -> str:
    phone = sub(r"[ ()-]", "", value.strip())
    if fullmatch(r"[6-9][0-9]{9}", phone):
        phone = "+91" + phone
    elif fullmatch(r"91[6-9][0-9]{9}", phone):
        phone = "+" + phone
    if not fullmatch(r"\+[1-9][0-9]{7,14}", phone):
        raise ValueError("Use an Indian mobile number or an international number with its country code")
    return phone


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(encoded: str | None, password: str) -> bool:
    try:
        return _hasher.verify(encoded or _dummy_hash, password) and encoded is not None
    except VerifyMismatchError:
        return False
    except (InvalidHashError, VerificationError):
        if encoded != _dummy_hash:
            verify_password(None, password)
        return False


def digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def read_account(row: sqlite3.Row) -> Account:
    return Account(
        row["id"], row["full_name"], row["normalized_phone_number"], row["role"], row["shop_id"],
        bool(row["is_active"]), row["created_at"], row["updated_at"],
    )


def create_account(
    db: sqlite3.Connection, full_name: str, phone: str, encoded: str, role: Role, shop_id: int | None,
) -> Account:
    row = db.execute(
        """
        INSERT INTO users (full_name, normalized_phone_number, password_hash, role, shop_id)
        VALUES (?, ?, ?, ?, ?) RETURNING *
        """,
        (full_name, phone, encoded, role, shop_id),
    ).fetchone()
    return read_account(row)


def linked_customer_scopes(db: sqlite3.Connection, user_id: int) -> list[tuple[int, int]]:
    return [tuple(row) for row in db.execute(
        """
        SELECT c.shop_id, c.id FROM customer_account_links AS link
        JOIN customers AS c ON c.id = link.customer_id
        WHERE link.user_id = ? ORDER BY c.shop_id, c.id
        """,
        (user_id,),
    )]


def session_token(value: str | None) -> str | None:
    return value if value and fullmatch(r"[A-Za-z0-9_-]{43}", value) else None


def csrf_token(raw_session: str, nonce: str) -> str:
    # Independent random nonce per session. The database alone cannot recover the token.
    return hmac_digest(raw_session.encode(), ("BoloHisaab CSRF " + nonce).encode(), "sha256").hex()


def new_session(db: sqlite3.Connection, user_id: int, now: int, previous: str | None) -> str:
    raw = token_urlsafe(32)
    nonce = token_urlsafe(32)
    if previous:
        revoke_session(db, digest(previous), now)
    db.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (now,))
    db.execute(
        """
        INSERT INTO auth_sessions (token_hash, user_id, csrf_nonce, csrf_hash, created_at, expires_at, last_activity_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (digest(raw), user_id, nonce, digest(csrf_token(raw, nonce)), now, now + SESSION_LIFETIME, now),
    )
    return raw


def revoke_session(db: sqlite3.Connection, token_hash: str, now: int) -> None:
    db.execute("UPDATE auth_sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL", (now, token_hash))


def verify_csrf(token: str | None, expected_hash: str) -> bool:
    return bool(token and len(token) == 64 and compare_digest(digest(token), expected_hash))


def reserve_attempt(db: sqlite3.Connection, purpose: str, phone: str, client_ip: str, now: int) -> int:
    window = now - now % ATTEMPT_WINDOW
    buckets = [(purpose + ":phone:" + digest(phone), 8 if purpose == "login" else 4),
               (purpose + ":ip:" + digest(client_ip), 30 if purpose == "login" else 15)]
    db.execute("DELETE FROM auth_attempt_limits WHERE window_start < ?", (window,))
    for key, limit in buckets:
        row = db.execute(
            "SELECT attempts FROM auth_attempt_limits WHERE bucket = ? AND window_start = ?", (key, window),
        ).fetchone()
        if row is not None and row["attempts"] >= limit:
            return window + ATTEMPT_WINDOW - now
    db.executemany(
        """
        INSERT INTO auth_attempt_limits (bucket, window_start, attempts) VALUES (?, ?, 1)
        ON CONFLICT(bucket, window_start) DO UPDATE SET attempts = attempts + 1
        """,
        [(key, window) for key, _ in buckets],
    )
    return 0
