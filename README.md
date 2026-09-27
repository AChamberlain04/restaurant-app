# Ember & Oak: a restaurant service app

A full-stack restaurant app built with **Python (Flask)**, **SQLite** and vanilla **HTML/CSS/JavaScript**. It has three parts:

- **Customers** browse the menu, build an order, and check out for pickup or dine-in.
- **Order tracking**: after checkout, customers get a live page that updates as the kitchen works on their order.
- **Reservations**: customers pick a date and party size, see which times are open, and book a table. The server won't let a time slot go over the dining room's capacity.
- **Staff dashboard**: staff log in to a kitchen board with Received → Preparing → Ready columns. From there they can advance or cancel tickets, check in reservations, mark menu items as sold out, and see today's stats.

## Quick start

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py                     # or: flask --app app run --debug
```

Open http://127.0.0.1:5000. On first run, the app creates `instance/restaurant.sqlite` and fills it with a sample menu.

**Staff login:** http://127.0.0.1:5000/staff (username `admin`, password `password123`)
Change these with the `STAFF_USERNAME` / `STAFF_PASSWORD` environment variables before the first run. Set `SECRET_KEY` in any real deployment.

To wipe the database and reseed it: `flask --app app init-db`

## Tests

```bash
python -m unittest discover tests -v     # or: pytest
```

There are 17 tests. They cover menu seeding, server-side pricing, validation, sold-out handling, the order status workflow, staff access control, reservation time rules, and seat capacity.

## Project layout

```
app.py            Flask app factory, business rules, page + JSON API routes
db.py             SQLite connection handling, schema init, seed data, `init-db` CLI
schema.sql        Tables: categories, menu_items, orders, order_items, reservations, staff
templates/        Jinja pages (base, index, track, reserve, login, staff)
static/           style.css + one JS file per page (common, order, track, reserve, staff)
tests/            unittest suite (pytest-compatible)
```

## REST API

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| GET | `/api/menu` | – | Categories, items, prices, availability, tax rate |
| POST | `/api/orders` | – | Place an order `{customer_name, phone, order_type, table_number?, notes?, items:[{id, quantity}]}` |
| GET | `/api/orders/<code>` | – | Track an order by its public code |
| GET | `/api/reservations/availability?date=&party_size=` | – | Open time slots for a day |
| POST | `/api/reservations` | – | Book `{name, phone, email?, party_size, reserved_for:"YYYY-MM-DDTHH:MM", notes?}` |
| GET | `/api/staff/orders?status=active` | staff | Active (or recent) orders with line items |
| PATCH | `/api/staff/orders/<id>` | staff | `{status}`: only valid transitions are allowed |
| GET | `/api/staff/reservations?date=` | staff | Reservations for a day |
| PATCH | `/api/staff/reservations/<id>` | staff | `{status: booked, seated, no_show, cancelled}` |
| PATCH | `/api/staff/menu/<id>` | staff | `{available?, price_cents?}` |
| GET | `/api/staff/stats` | staff | Orders, revenue, active orders, and reserved covers for today |

## Design decisions worth talking about

- **Prices are never trusted from the client.** The browser sends only item IDs and quantities. The server looks up the current prices, merges duplicate lines, and calculates tax. Each order line also stores the item's name and price at the time of ordering, so changing the menu later doesn't change old receipts.
- **Money is stored as integer cents**, which avoids floating-point rounding errors.
- **Order status is a state machine** (`ORDER_FLOW` in `app.py`). An order can't skip from "received" to "completed", and finished orders can't be reopened.
- **Reservation capacity** is checked against the seats already booked in each 30-minute slot. Cancelled and no-show bookings free their seats back up.
- **Public tracking codes** are random 6-character hex strings rather than sequential IDs, so customers can't guess other people's orders. The tracking endpoint also leaves out the customer's phone number.
- **Staff routes** use a session-based decorator. Passwords are hashed with Werkzeug, and the session cookie is HttpOnly with SameSite=Lax.

Business rules (tax rate, opening hours, slot length, seats per slot, table count) are constants at the top of `app.py`.

## Ideas for next steps

- Online payments (Stripe Checkout)
- Text message notifications when an order is ready (Twilio)
- Switch to SQLAlchemy + PostgreSQL and deploy (Render, Railway, Fly.io)
- Push updates to the kitchen board over WebSockets instead of polling
- A menu editor for adding, editing, and uploading photos of items
