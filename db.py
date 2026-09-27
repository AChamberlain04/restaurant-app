"""Database helpers: connection per request, schema creation and seed data."""
import sqlite3
from pathlib import Path

import click
from flask import current_app, g
from werkzeug.security import generate_password_hash

SCHEMA = Path(__file__).with_name("schema.sql")

SEED_MENU = {
    "Starters": [
        ("Garlic Knots", "Six house-baked knots, parmesan, marinara for dipping.", 695, "vegetarian"),
        ("Crispy Calamari", "Lightly fried, lemon aioli, charred lemon.", 1295, ""),
        ("Buffalo Cauliflower", "Tossed in house hot sauce with blue cheese dip.", 995, "vegetarian,spicy"),
    ],
    "Mains": [
        ("Smash Burger", "Two beef patties, American cheese, pickles, special sauce, fries.", 1595, ""),
        ("Chicken Parm", "Breaded cutlet, marinara, mozzarella, over spaghetti.", 1895, ""),
        ("Blackened Salmon", "Cajun spice, rice pilaf, seasonal vegetables.", 2295, "gf,spicy"),
        ("Mushroom Risotto", "Arborio rice, wild mushrooms, truffle oil, parmesan.", 1795, "vegetarian,gf"),
    ],
    "Pizza": [
        ("Margherita", "San Marzano tomato, fresh mozzarella, basil.", 1395, "vegetarian"),
        ("Pepperoni & Hot Honey", "Cup-and-char pepperoni, mozzarella, chili honey drizzle.", 1595, "spicy"),
    ],
    "Desserts": [
        ("Tiramisu", "Espresso-soaked ladyfingers, mascarpone, cocoa.", 895, "vegetarian"),
        ("Molten Chocolate Cake", "Warm center, vanilla ice cream.", 950, "vegetarian"),
    ],
    "Drinks": [
        ("Fresh Lemonade", "Squeezed daily. Free refills.", 395, "vegetarian,gf"),
        ("Iced Tea", "Sweet or unsweet.", 295, "vegetarian,gf"),
        ("Craft Root Beer", "Local small-batch, glass bottle.", 450, "vegetarian,gf"),
    ],
}


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(seed: bool = True):
    db = get_db()
    db.executescript(SCHEMA.read_text())
    if seed:
        for position, (category, items) in enumerate(SEED_MENU.items()):
            cur = db.execute(
                "INSERT INTO categories (name, sort_order) VALUES (?, ?)", (category, position)
            )
            db.executemany(
                "INSERT INTO menu_items (category_id, name, description, price_cents, tags)"
                " VALUES (?, ?, ?, ?, ?)",
                [(cur.lastrowid, *item) for item in items],
            )
        db.execute(
            "INSERT INTO staff (username, password_hash) VALUES (?, ?)",
            (
                current_app.config["STAFF_USERNAME"],
                generate_password_hash(current_app.config["STAFF_PASSWORD"], method="pbkdf2:sha256"),
            ),
        )
    db.commit()


@click.command("init-db")
def init_db_command():
    """Drop and recreate all tables, then load the sample menu."""
    init_db()
    click.echo("Database initialised with sample menu and staff account.")


def register(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
