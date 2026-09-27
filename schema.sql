DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS reservations;
DROP TABLE IF EXISTS menu_items;
DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS staff;

CREATE TABLE categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE menu_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id  INTEGER NOT NULL REFERENCES categories(id),
    name         TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    price_cents  INTEGER NOT NULL CHECK (price_cents >= 0),
    tags         TEXT NOT NULL DEFAULT '',          -- comma separated: vegetarian,spicy,gf
    available    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT NOT NULL UNIQUE,           -- public tracking code
    customer_name   TEXT NOT NULL,
    phone           TEXT NOT NULL,
    order_type      TEXT NOT NULL CHECK (order_type IN ('pickup', 'dine_in')),
    table_number    INTEGER,
    notes           TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'received'
                    CHECK (status IN ('received', 'preparing', 'ready', 'completed', 'cancelled')),
    subtotal_cents  INTEGER NOT NULL,
    tax_cents       INTEGER NOT NULL,
    total_cents     INTEGER NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE order_items (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id          INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    menu_item_id      INTEGER NOT NULL REFERENCES menu_items(id),
    name              TEXT NOT NULL,                -- snapshot at time of order
    unit_price_cents  INTEGER NOT NULL,
    quantity          INTEGER NOT NULL CHECK (quantity > 0)
);

CREATE TABLE reservations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    phone        TEXT NOT NULL,
    email        TEXT NOT NULL DEFAULT '',
    party_size   INTEGER NOT NULL CHECK (party_size BETWEEN 1 AND 12),
    reserved_for TEXT NOT NULL,                     -- ISO 'YYYY-MM-DDTHH:MM'
    notes        TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'booked'
                 CHECK (status IN ('booked', 'seated', 'cancelled', 'no_show')),
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE staff (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    username       TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL
);

CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_reservations_time ON reservations(reserved_for);
