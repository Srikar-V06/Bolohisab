ALTER TABLE customers ADD COLUMN normalized_phone_number TEXT;
ALTER TABLE customer_account_links RENAME TO legacy_customer_links;

CREATE TABLE store_customer_links (
    id INTEGER PRIMARY KEY,
    customer_user_id INTEGER NOT NULL,
    role TEXT NOT NULL DEFAULT 'CUSTOMER' CHECK (role = 'CUSTOMER'),
    store_id INTEGER NOT NULL REFERENCES shops(id),
    store_customer_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','REVOKED')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    linked_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    revoked_at TEXT,
    CHECK ((status = 'REVOKED') = (revoked_at IS NOT NULL)),
    FOREIGN KEY (customer_user_id,role) REFERENCES users(id,role),
    FOREIGN KEY (store_id,store_customer_id) REFERENCES customers(shop_id,id)
) STRICT;
CREATE UNIQUE INDEX active_ledger_link ON store_customer_links(store_customer_id) WHERE status='ACTIVE';
CREATE INDEX account_store_links ON store_customer_links(customer_user_id,store_id,status);
INSERT INTO store_customer_links(customer_user_id,store_id,store_customer_id)
SELECT l.user_id,c.shop_id,c.id FROM legacy_customer_links l JOIN customers c ON c.id=l.customer_id;
DROP TABLE legacy_customer_links;

-- Preserve any historical same-shop records. New links have a single unambiguous store route.
CREATE TRIGGER one_store_link BEFORE INSERT ON store_customer_links
WHEN NEW.status='ACTIVE' AND EXISTS (SELECT 1 FROM store_customer_links WHERE
    customer_user_id=NEW.customer_user_id AND store_id=NEW.store_id AND status='ACTIVE')
BEGIN SELECT RAISE(ABORT,'Account already linked to store'); END;

CREATE VIEW customer_account_links AS
SELECT store_customer_id AS customer_id,customer_user_id AS user_id,role
FROM store_customer_links WHERE status='ACTIVE';
CREATE TRIGGER operator_customer_link INSTEAD OF INSERT ON customer_account_links
BEGIN
    INSERT INTO store_customer_links(customer_user_id,store_id,store_customer_id)
    VALUES (NEW.user_id,(SELECT shop_id FROM customers WHERE id=NEW.customer_id),NEW.customer_id);
END;

CREATE TABLE customer_invitations (
    id INTEGER PRIMARY KEY,
    store_id INTEGER NOT NULL REFERENCES shops(id),
    store_customer_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE CHECK (length(token_hash)=64),
    expires_at INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PENDING','REVOKED','EXPIRED','CLAIMED')),
    FOREIGN KEY (store_id,store_customer_id) REFERENCES customers(shop_id,id)
) STRICT;
CREATE UNIQUE INDEX pending_invitation ON customer_invitations(store_customer_id) WHERE status='PENDING';
CREATE INDEX invitation_history ON customer_invitations(store_customer_id,id DESC);

CREATE UNIQUE INDEX receipt_scope ON receipts(shop_id,customer_id,id);
CREATE TABLE notifications (
    id INTEGER PRIMARY KEY,
    customer_user_id INTEGER NOT NULL REFERENCES users(id),
    store_id INTEGER NOT NULL REFERENCES shops(id),
    store_customer_id INTEGER NOT NULL,
    receipt_id INTEGER NOT NULL,
    notification_type TEXT NOT NULL DEFAULT 'RECEIPT_AVAILABLE' CHECK(notification_type='RECEIPT_AVAILABLE'),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    read_at TEXT,
    UNIQUE(receipt_id,customer_user_id),
    FOREIGN KEY(store_id,store_customer_id) REFERENCES customers(shop_id,id),
    FOREIGN KEY(store_id,store_customer_id,receipt_id) REFERENCES receipts(shop_id,customer_id,id)
) STRICT;
CREATE INDEX notification_feed ON notifications(customer_user_id,id DESC);
CREATE INDEX notification_unread ON notifications(customer_user_id,store_id,store_customer_id) WHERE read_at IS NULL;
