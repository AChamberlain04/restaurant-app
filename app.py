"""Ember & Oak — a full-stack restaurant service app built with Flask + SQLite.

Customers: browse the menu, order for pickup or dine-in, track the order live,
and book a table. Staff: log in to a kitchen dashboard to move orders through
their lifecycle, manage reservations and mark menu items sold out.
"""
import os
import secrets
from datetime import date, datetime, time, timedelta
from functools import wraps

from flask import (
    Flask, abort, jsonify, redirect, render_template, request, session, url_for,
)
from werkzeug.security import check_password_hash

import db as database
from db import get_db

# ---------------------------------------------------------------------------
# Business rules (tweak these to fit the restaurant)
# ---------------------------------------------------------------------------
TAX_RATE = 0.06
OPEN_TIME = time(11, 0)
LAST_SEATING = time(21, 0)
SLOT_MINUTES = 30
SEATS_PER_SLOT = 40          # total guests the dining room can seat per 30-min slot
MAX_QTY_PER_LINE = 20
TABLE_COUNT = 30

ORDER_FLOW = {                # allowed status transitions
    "received": {"preparing", "cancelled"},
    "preparing": {"ready", "cancelled"},
    "ready": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}
RESERVATION_STATUSES = {"booked", "seated", "cancelled", "no_show"}


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-change-me"),
        DATABASE=os.path.join(app.instance_path, "restaurant.sqlite"),
        STAFF_USERNAME=os.environ.get("STAFF_USERNAME", "admin"),
        STAFF_PASSWORD=os.environ.get("STAFF_PASSWORD", "password123"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if test_config:
        app.config.update(test_config)
    os.makedirs(app.instance_path, exist_ok=True)

    database.register(app)

    # Create + seed the database automatically on first run.
    with app.app_context():
        exists = get_db().execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='menu_items'"
        ).fetchone()
        if not exists:
            database.init_db()

    register_routes(app)
    return app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class ValidationError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message, self.status = message, status


def require_text(data, field, max_len=120):
    value = str(data.get(field, "")).strip()
    if not value:
        raise ValidationError(f"'{field}' is required.")
    if len(value) > max_len:
        raise ValidationError(f"'{field}' must be {max_len} characters or fewer.")
    return value


def optional_text(data, field, max_len=500):
    value = str(data.get(field) or "").strip()
    if len(value) > max_len:
        raise ValidationError(f"'{field}' must be {max_len} characters or fewer.")
    return value


def require_int(data, field, lo, hi):
    try:
        value = int(data.get(field))
    except (TypeError, ValueError):
        raise ValidationError(f"'{field}' must be a whole number.")
    if not lo <= value <= hi:
        raise ValidationError(f"'{field}' must be between {lo} and {hi}.")
    return value


def json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object.")
    return data


def staff_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("staff_id"):
            if request.path.startswith("/api/"):
                return jsonify(error="Staff login required."), 401
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def serialize_order(order, items):
    return {
        "id": order["id"],
        "code": order["code"],
        "customer_name": order["customer_name"],
        "phone": order["phone"],
        "order_type": order["order_type"],
        "table_number": order["table_number"],
        "notes": order["notes"],
        "status": order["status"],
        "subtotal_cents": order["subtotal_cents"],
        "tax_cents": order["tax_cents"],
        "total_cents": order["total_cents"],
        "created_at": order["created_at"],
        "updated_at": order["updated_at"],
        "items": [
            {
                "menu_item_id": i["menu_item_id"],
                "name": i["name"],
                "unit_price_cents": i["unit_price_cents"],
                "quantity": i["quantity"],
            }
            for i in items
        ],
    }


def load_order(where, param):
    db = get_db()
    order = db.execute(f"SELECT * FROM orders WHERE {where} = ?", (param,)).fetchone()
    if order is None:
        return None
    items = db.execute(
        "SELECT * FROM order_items WHERE order_id = ? ORDER BY id", (order["id"],)
    ).fetchall()
    return serialize_order(order, items)


def slot_times():
    t = datetime.combine(date.today(), OPEN_TIME)
    end = datetime.combine(date.today(), LAST_SEATING)
    while t <= end:
        yield t.time()
        t += timedelta(minutes=SLOT_MINUTES)


def seats_booked(slot_iso):
    row = get_db().execute(
        "SELECT COALESCE(SUM(party_size), 0) AS n FROM reservations"
        " WHERE reserved_for = ? AND status IN ('booked', 'seated')",
        (slot_iso,),
    ).fetchone()
    return row["n"]


def parse_slot(value):
    try:
        when = datetime.strptime(str(value), "%Y-%m-%dT%H:%M")
    except ValueError:
        raise ValidationError("'reserved_for' must look like 2026-10-01T18:30.")
    if when.time() not in set(slot_times()):
        raise ValidationError(
            f"Reservations are every {SLOT_MINUTES} minutes from "
            f"{OPEN_TIME:%H:%M} to {LAST_SEATING:%H:%M}."
        )
    if when <= datetime.now():
        raise ValidationError("Reservation time must be in the future.")
    if when.date() > date.today() + timedelta(days=60):
        raise ValidationError("Reservations open up to 60 days in advance.")
    return when


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
def register_routes(app):

    @app.errorhandler(ValidationError)
    def handle_validation(err):
        return jsonify(error=err.message), err.status

    # ----- Pages -----------------------------------------------------------
    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/track/<code>")
    def track(code):
        return render_template("track.html", code=code.upper())

    @app.get("/reserve")
    def reserve():
        return render_template("reserve.html")

    @app.route("/staff/login", methods=["GET", "POST"])
    def login():
        error = None
        if request.method == "POST":
            user = get_db().execute(
                "SELECT * FROM staff WHERE username = ?", (request.form.get("username", ""),)
            ).fetchone()
            if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
                session.clear()
                session["staff_id"] = user["id"]
                session["staff_name"] = user["username"]
                nxt = request.args.get("next", "")
                return redirect(nxt if nxt.startswith("/staff") else url_for("dashboard"))
            error = "Incorrect username or password."
        return render_template("login.html", error=error)

    @app.post("/staff/logout")
    def logout():
        session.clear()
        return redirect(url_for("index"))

    @app.get("/staff")
    @staff_required
    def dashboard():
        return render_template("staff.html", staff_name=session.get("staff_name"))

    # ----- Public API: menu --------------------------------------------------
    @app.get("/api/menu")
    def api_menu():
        db = get_db()
        cats = db.execute("SELECT * FROM categories ORDER BY sort_order").fetchall()
        items = db.execute("SELECT * FROM menu_items ORDER BY id").fetchall()
        return jsonify(
            tax_rate=TAX_RATE,
            categories=[
                {
                    "id": c["id"],
                    "name": c["name"],
                    "items": [
                        {
                            "id": i["id"],
                            "name": i["name"],
                            "description": i["description"],
                            "price_cents": i["price_cents"],
                            "tags": [t for t in i["tags"].split(",") if t],
                            "available": bool(i["available"]),
                        }
                        for i in items
                        if i["category_id"] == c["id"]
                    ],
                }
                for c in cats
            ],
        )

    # ----- Public API: orders ------------------------------------------------
    @app.post("/api/orders")
    def api_create_order():
        data = json_body()
        name = require_text(data, "customer_name", 80)
        phone = require_text(data, "phone", 30)
        notes = optional_text(data, "notes", 300)
        order_type = data.get("order_type", "pickup")
        if order_type not in ("pickup", "dine_in"):
            raise ValidationError("'order_type' must be 'pickup' or 'dine_in'.")
        table = require_int(data, "table_number", 1, TABLE_COUNT) if order_type == "dine_in" else None

        lines = data.get("items")
        if not isinstance(lines, list) or not lines:
            raise ValidationError("Your order needs at least one item.")

        db = get_db()
        # Merge duplicate lines and price everything server-side (never trust client prices).
        wanted = {}
        for line in lines:
            if not isinstance(line, dict):
                raise ValidationError("Each item must be an object with id and quantity.")
            item_id = require_int(line, "id", 1, 10**9)
            qty = require_int(line, "quantity", 1, MAX_QTY_PER_LINE)
            wanted[item_id] = wanted.get(item_id, 0) + qty

        priced = []
        for item_id, qty in wanted.items():
            item = db.execute("SELECT * FROM menu_items WHERE id = ?", (item_id,)).fetchone()
            if item is None:
                raise ValidationError(f"Menu item {item_id} does not exist.")
            if not item["available"]:
                raise ValidationError(f"Sorry, {item['name']} is sold out right now.", 409)
            if qty > MAX_QTY_PER_LINE:
                raise ValidationError(f"Maximum {MAX_QTY_PER_LINE} of any one item per order.")
            priced.append((item, qty))

        subtotal = sum(item["price_cents"] * qty for item, qty in priced)
        tax = round(subtotal * TAX_RATE)
        code = secrets.token_hex(3).upper()

        cur = db.execute(
            "INSERT INTO orders (code, customer_name, phone, order_type, table_number, notes,"
            " subtotal_cents, tax_cents, total_cents) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (code, name, phone, order_type, table, notes, subtotal, tax, subtotal + tax),
        )
        db.executemany(
            "INSERT INTO order_items (order_id, menu_item_id, name, unit_price_cents, quantity)"
            " VALUES (?, ?, ?, ?, ?)",
            [(cur.lastrowid, item["id"], item["name"], item["price_cents"], qty) for item, qty in priced],
        )
        db.commit()
        return jsonify(load_order("id", cur.lastrowid)), 201

    @app.get("/api/orders/<code>")
    def api_track_order(code):
        order = load_order("code", code.upper())
        if order is None:
            abort(404)
        # Customers tracking by code don't need the phone number echoed back.
        order.pop("phone", None)
        return jsonify(order)

    # ----- Public API: reservations -----------------------------------------
    @app.get("/api/reservations/availability")
    def api_availability():
        try:
            day = datetime.strptime(request.args.get("date", ""), "%Y-%m-%d").date()
        except ValueError:
            raise ValidationError("Pass ?date=YYYY-MM-DD.")
        party = require_int(request.args, "party_size", 1, 12)
        now = datetime.now()
        slots = []
        for t in slot_times():
            when = datetime.combine(day, t)
            iso = when.strftime("%Y-%m-%dT%H:%M")
            left = SEATS_PER_SLOT - seats_booked(iso)
            slots.append({
                "time": t.strftime("%H:%M"),
                "value": iso,
                "available": when > now and left >= party,
            })
        return jsonify(date=day.isoformat(), party_size=party, slots=slots)

    @app.post("/api/reservations")
    def api_create_reservation():
        data = json_body()
        name = require_text(data, "name", 80)
        phone = require_text(data, "phone", 30)
        email = optional_text(data, "email", 120)
        notes = optional_text(data, "notes", 300)
        party = require_int(data, "party_size", 1, 12)
        when = parse_slot(data.get("reserved_for"))
        iso = when.strftime("%Y-%m-%dT%H:%M")

        db = get_db()
        if seats_booked(iso) + party > SEATS_PER_SLOT:
            raise ValidationError("That time is fully booked — please pick another slot.", 409)
        cur = db.execute(
            "INSERT INTO reservations (name, phone, email, party_size, reserved_for, notes)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (name, phone, email, party, iso, notes),
        )
        db.commit()
        row = db.execute("SELECT * FROM reservations WHERE id = ?", (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)), 201

    # ----- Staff API ---------------------------------------------------------
    @app.get("/api/staff/orders")
    @staff_required
    def api_staff_orders():
        status = request.args.get("status")
        db = get_db()
        if status == "active":
            rows = db.execute(
                "SELECT id FROM orders WHERE status IN ('received','preparing','ready')"
                " ORDER BY created_at, id"
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT id FROM orders ORDER BY created_at DESC, id DESC LIMIT 100"
            ).fetchall()
        return jsonify([load_order("id", r["id"]) for r in rows])

    @app.patch("/api/staff/orders/<int:order_id>")
    @staff_required
    def api_update_order(order_id):
        new_status = json_body().get("status")
        db = get_db()
        order = db.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()
        if order is None:
            abort(404)
        if new_status not in ORDER_FLOW.get(order["status"], set()):
            raise ValidationError(
                f"Can't move an order from '{order['status']}' to '{new_status}'.", 409
            )
        db.execute(
            "UPDATE orders SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (new_status, order_id),
        )
        db.commit()
        return jsonify(load_order("id", order_id))

    @app.get("/api/staff/reservations")
    @staff_required
    def api_staff_reservations():
        day = request.args.get("date") or date.today().isoformat()
        rows = get_db().execute(
            "SELECT * FROM reservations WHERE substr(reserved_for, 1, 10) = ?"
            " ORDER BY reserved_for, id",
            (day,),
        ).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.patch("/api/staff/reservations/<int:res_id>")
    @staff_required
    def api_update_reservation(res_id):
        status = json_body().get("status")
        if status not in RESERVATION_STATUSES:
            raise ValidationError(f"Status must be one of {sorted(RESERVATION_STATUSES)}.")
        db = get_db()
        if db.execute("UPDATE reservations SET status = ? WHERE id = ?", (status, res_id)).rowcount == 0:
            abort(404)
        db.commit()
        return jsonify(dict(db.execute("SELECT * FROM reservations WHERE id = ?", (res_id,)).fetchone()))

    @app.patch("/api/staff/menu/<int:item_id>")
    @staff_required
    def api_update_menu_item(item_id):
        data = json_body()
        db = get_db()
        if db.execute("SELECT 1 FROM menu_items WHERE id = ?", (item_id,)).fetchone() is None:
            abort(404)
        if "available" in data:
            db.execute("UPDATE menu_items SET available = ? WHERE id = ?", (1 if data["available"] else 0, item_id))
        if "price_cents" in data:
            price = require_int(data, "price_cents", 0, 100_000)
            db.execute("UPDATE menu_items SET price_cents = ? WHERE id = ?", (price, item_id))
        db.commit()
        return jsonify(dict(db.execute("SELECT * FROM menu_items WHERE id = ?", (item_id,)).fetchone()))

    @app.get("/api/staff/stats")
    @staff_required
    def api_stats():
        db = get_db()
        today = db.execute(
            "SELECT COUNT(*) AS orders, COALESCE(SUM(total_cents), 0) AS revenue FROM orders"
            " WHERE date(created_at) = date('now') AND status != 'cancelled'"
        ).fetchone()
        active = db.execute(
            "SELECT COUNT(*) AS n FROM orders WHERE status IN ('received','preparing','ready')"
        ).fetchone()
        covers = db.execute(
            "SELECT COALESCE(SUM(party_size), 0) AS n FROM reservations"
            " WHERE substr(reserved_for, 1, 10) = ? AND status IN ('booked','seated')",
            (date.today().isoformat(),),
        ).fetchone()
        return jsonify(
            orders_today=today["orders"],
            revenue_today_cents=today["revenue"],
            active_orders=active["n"],
            covers_today=covers["n"],
        )


if __name__ == "__main__":
    # `python app.py` or `flask --app app run --debug` (Flask finds create_app automatically)
    create_app().run(debug=True)
