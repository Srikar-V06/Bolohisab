ALTER TABLE shops ADD COLUMN address TEXT CHECK (address IS NULL OR length(address) <= 500);

CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL CHECK (length(trim(full_name)) BETWEEN 1 AND 120),
    normalized_phone_number TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('SHOPKEEPER', 'CUSTOMER')),
    shop_id INTEGER UNIQUE REFERENCES shops(id),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK ((role = 'SHOPKEEPER') = (shop_id IS NOT NULL)),
    UNIQUE (id, role)
) STRICT;

-- Existing ledger records remain unlinked unless an operator explicitly links them.
CREATE TABLE customer_account_links (
    customer_id INTEGER PRIMARY KEY REFERENCES customers(id),
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL DEFAULT 'CUSTOMER' CHECK (role = 'CUSTOMER'),
    FOREIGN KEY (user_id, role) REFERENCES users(id, role)
) STRICT;
CREATE INDEX customer_account_links_user ON customer_account_links(user_id, customer_id);

CREATE TABLE auth_sessions (
    token_hash TEXT PRIMARY KEY CHECK (length(token_hash) = 64),
    user_id INTEGER NOT NULL REFERENCES users(id),
    csrf_nonce TEXT NOT NULL,
    csrf_hash TEXT NOT NULL CHECK (length(csrf_hash) = 64),
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL CHECK (expires_at > created_at),
    last_activity_at INTEGER NOT NULL CHECK (last_activity_at >= created_at),
    revoked_at INTEGER
) STRICT;
CREATE INDEX auth_sessions_user ON auth_sessions(user_id);
CREATE INDEX auth_sessions_expiry ON auth_sessions(expires_at);

CREATE TRIGGER user_account_updated
AFTER UPDATE OF full_name, normalized_phone_number, password_hash, role, shop_id, is_active ON users
BEGIN
    UPDATE users SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = NEW.id;
    UPDATE auth_sessions SET revoked_at = unixepoch()
    WHERE user_id = NEW.id AND revoked_at IS NULL AND (
        NEW.is_active = 0 OR NEW.password_hash <> OLD.password_hash
        OR NEW.role <> OLD.role OR NEW.shop_id IS NOT OLD.shop_id
    );
END;

CREATE TABLE auth_attempt_limits (
    bucket TEXT NOT NULL,
    window_start INTEGER NOT NULL,
    attempts INTEGER NOT NULL CHECK (attempts > 0),
    PRIMARY KEY (bucket, window_start)
) STRICT;
CREATE INDEX auth_attempt_window ON auth_attempt_limits(window_start);

ALTER TABLE correction_requests ADD COLUMN reviewed_by_user_id INTEGER REFERENCES users(id);

CREATE TRIGGER receipt_dispute_reviewer_scope
BEFORE UPDATE OF reviewed_by_user_id ON correction_requests
WHEN NEW.reviewed_by_user_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM users WHERE id = NEW.reviewed_by_user_id AND shop_id = NEW.shop_id AND is_active = 1
)
BEGIN
    SELECT RAISE(ABORT, 'Reviewer must own the shop');
END;
