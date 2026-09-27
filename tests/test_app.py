"""API tests. Run with:  python -m unittest discover tests   (or: pytest)"""
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import SEATS_PER_SLOT, create_app  # noqa: E402

TOMORROW_7PM = f"{date.today() + timedelta(days=1)}T19:00"


class RestaurantTestCase(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.app = create_app({"TESTING": True, "DATABASE": self.db_path, "SECRET_KEY": "test"})
        self.client = self.app.test_client()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    # -- helpers --
    def login(self):
        return self.client.post("/staff/login", data={"username": "admin", "password": "password123"})

    def first_item(self):
        return self.client.get("/api/menu").get_json()["categories"][0]["items"][0]

    def place_order(self, **overrides):
        body = {
            "customer_name": "Adam",
            "phone": "555-0100",
            "order_type": "pickup",
            "items": [{"id": self.first_item()["id"], "quantity": 2}],
        }
        body.update(overrides)
        return self.client.post("/api/orders", json=body)


class MenuTests(RestaurantTestCase):
    def test_menu_is_seeded(self):
        data = self.client.get("/api/menu").get_json()
        self.assertGreaterEqual(len(data["categories"]), 4)
        self.assertTrue(all(c["items"] for c in data["categories"]))

    def test_pages_render(self):
        for path in ["/", "/reserve", "/track/ABC123", "/staff/login"]:
            self.assertEqual(self.client.get(path).status_code, 200, path)


class OrderTests(RestaurantTestCase):
    def test_order_totals_are_computed_server_side(self):
        item = self.first_item()
        res = self.place_order(items=[{"id": item["id"], "quantity": 2, "price_cents": 1}])
        self.assertEqual(res.status_code, 201)
        order = res.get_json()
        self.assertEqual(order["subtotal_cents"], item["price_cents"] * 2)
        self.assertEqual(order["total_cents"], order["subtotal_cents"] + order["tax_cents"])
        self.assertEqual(order["status"], "received")

    def test_duplicate_lines_are_merged(self):
        item_id = self.first_item()["id"]
        order = self.place_order(items=[{"id": item_id, "quantity": 1}, {"id": item_id, "quantity": 2}]).get_json()
        self.assertEqual(len(order["items"]), 1)
        self.assertEqual(order["items"][0]["quantity"], 3)

    def test_tracking_hides_phone(self):
        code = self.place_order().get_json()["code"]
        tracked = self.client.get(f"/api/orders/{code.lower()}").get_json()
        self.assertEqual(tracked["code"], code)
        self.assertNotIn("phone", tracked)

    def test_unknown_order_404(self):
        self.assertEqual(self.client.get("/api/orders/ZZZZZZ").status_code, 404)

    def test_validation_errors(self):
        self.assertEqual(self.place_order(customer_name="").status_code, 400)
        self.assertEqual(self.place_order(items=[]).status_code, 400)
        self.assertEqual(self.place_order(items=[{"id": 99999, "quantity": 1}]).status_code, 400)
        self.assertEqual(self.place_order(items=[{"id": 1, "quantity": 0}]).status_code, 400)
        self.assertEqual(self.place_order(order_type="dine_in").status_code, 400)  # no table
        self.assertEqual(self.place_order(order_type="dine_in", table_number=5).status_code, 201)
        self.assertEqual(self.client.post("/api/orders", data="nope").status_code, 400)

    def test_sold_out_item_rejected(self):
        self.login()
        item_id = self.first_item()["id"]
        self.client.patch(f"/api/staff/menu/{item_id}", json={"available": False})
        res = self.place_order()
        self.assertEqual(res.status_code, 409)
        self.assertIn("sold out", res.get_json()["error"])


class StaffTests(RestaurantTestCase):
    def test_staff_endpoints_require_login(self):
        self.assertEqual(self.client.get("/api/staff/orders").status_code, 401)
        self.assertEqual(self.client.patch("/api/staff/orders/1", json={"status": "preparing"}).status_code, 401)
        self.assertEqual(self.client.get("/staff").status_code, 302)

    def test_bad_login(self):
        res = self.client.post("/staff/login", data={"username": "admin", "password": "wrong"})
        self.assertIn(b"Incorrect", res.data)

    def test_order_lifecycle(self):
        order_id = self.place_order().get_json()["id"]
        self.login()
        for status in ["preparing", "ready", "completed"]:
            res = self.client.patch(f"/api/staff/orders/{order_id}", json={"status": status})
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.get_json()["status"], status)
        # completed orders can't move anymore
        res = self.client.patch(f"/api/staff/orders/{order_id}", json={"status": "cancelled"})
        self.assertEqual(res.status_code, 409)

    def test_cannot_skip_steps(self):
        order_id = self.place_order().get_json()["id"]
        self.login()
        res = self.client.patch(f"/api/staff/orders/{order_id}", json={"status": "completed"})
        self.assertEqual(res.status_code, 409)

    def test_active_filter_and_stats(self):
        self.place_order()
        self.place_order()
        self.login()
        self.assertEqual(len(self.client.get("/api/staff/orders?status=active").get_json()), 2)
        stats = self.client.get("/api/staff/stats").get_json()
        self.assertEqual(stats["active_orders"], 2)
        self.assertEqual(stats["orders_today"], 2)


class ReservationTests(RestaurantTestCase):
    def book(self, **overrides):
        body = {"name": "Adam", "phone": "555-0100", "party_size": 4, "reserved_for": TOMORROW_7PM}
        body.update(overrides)
        return self.client.post("/api/reservations", json=body)

    def test_book_and_list(self):
        res = self.book()
        self.assertEqual(res.status_code, 201)
        self.login()
        day = TOMORROW_7PM[:10]
        rows = self.client.get(f"/api/staff/reservations?date={day}").get_json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["party_size"], 4)

    def test_rejects_bad_times(self):
        tomorrow = TOMORROW_7PM[:10]
        self.assertEqual(self.book(reserved_for=f"{tomorrow}T19:15").status_code, 400)  # off-slot
        self.assertEqual(self.book(reserved_for=f"{tomorrow}T23:00").status_code, 400)  # closed
        self.assertEqual(self.book(reserved_for="2020-01-01T19:00").status_code, 400)   # past
        self.assertEqual(self.book(reserved_for="tonight").status_code, 400)
        self.assertEqual(self.book(party_size=20).status_code, 400)

    def test_capacity_is_enforced(self):
        booked = 0
        while booked + 12 <= SEATS_PER_SLOT:
            self.assertEqual(self.book(party_size=12).status_code, 201)
            booked += 12
        remaining = SEATS_PER_SLOT - booked
        self.assertEqual(self.book(party_size=remaining + 1).status_code, 409)
        avail = self.client.get(
            f"/api/reservations/availability?date={TOMORROW_7PM[:10]}&party_size={remaining + 1}"
        ).get_json()
        slot = next(s for s in avail["slots"] if s["time"] == "19:00")
        self.assertFalse(slot["available"])

    def test_cancelled_reservation_frees_seats(self):
        ids = []
        booked = 0
        while booked + 12 <= SEATS_PER_SLOT:
            ids.append(self.book(party_size=12).get_json()["id"])
            booked += 12
        self.login()
        self.client.patch(f"/api/staff/reservations/{ids[0]}", json={"status": "cancelled"})
        self.assertEqual(self.book(party_size=12).status_code, 201)


if __name__ == "__main__":
    unittest.main()
