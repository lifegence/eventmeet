import frappe

from eventmeet.services import registration as reg_service
from eventmeet.services import seats
from eventmeet.tests.utils import SeminarTestCase, capture_mail, make_seminar


def register_many(seminar, count, ticket="General"):
	for i in range(count):
		reg_service.create_registration(seminar.name, ticket, f"User {i}", f"user{i}@example.com", "ACME", "")


def set_settings(mode=None, threshold=None):
	frappe.db.set_single_value(
		"Seminar Settings", {"seat_display": mode, "seat_display_threshold": threshold}
	)
	frappe.clear_document_cache("Seminar Settings", "Seminar Settings")


def page_tickets(seminar):
	context = frappe._dict()
	frappe.get_doc("Seminar", seminar.name).get_context(context)
	return {t["ticket"].ticket_name: t for t in context.tickets}


class TestSeatAvailability(SeminarTestCase):
	def test_exact_shows_the_number(self):
		self.assertEqual(seats.availability(47, seats.EXACT, 10)["remaining"], 47)

	def test_threshold_hides_the_number_above_the_threshold(self):
		result = seats.availability(11, seats.THRESHOLD, 10)
		self.assertIsNone(result["remaining"])
		self.assertFalse(result["sold_out"])
		self.assertEqual(result["label"], "Seats available")

	def test_threshold_shows_the_number_at_the_threshold(self):
		result = seats.availability(10, seats.THRESHOLD, 10)
		self.assertEqual(result["remaining"], 10)
		self.assertEqual(result["label"], "Only 10 seats left")

	def test_hidden_never_shows_the_number(self):
		self.assertIsNone(seats.availability(1, seats.HIDDEN, 10)["remaining"])

	def test_sold_out_in_every_mode(self):
		for mode in seats.MODES:
			self.assertTrue(seats.availability(0, mode, 10)["sold_out"], mode)

	def test_no_capacity_shows_nothing(self):
		self.assertEqual(
			seats.availability(None, seats.HIDDEN, 10), {"sold_out": False, "remaining": None, "label": None}
		)

	def test_ticket_overrides_seminar_overrides_settings(self):
		settings = {"seat_display": "Hidden", "seat_display_threshold": 20}
		seminar = {"seat_display": "Threshold", "seat_display_threshold": 0}
		self.assertEqual(seats.resolve(settings, seminar, {}), ("Threshold", 20))
		self.assertEqual(seats.resolve(settings, seminar, {"seat_display": "Exact"}), ("Exact", 20))
		self.assertEqual(seats.resolve(settings, {}, {}), ("Hidden", 20))
		self.assertEqual(seats.resolve({}, {}, {}), ("Exact", seats.DEFAULT_THRESHOLD))


class TestSeatDisplayOnPage(SeminarTestCase):
	def setUp(self):
		self.mail = capture_mail(self)
		set_settings()
		self.addCleanup(set_settings)

	def test_default_stays_exact(self):
		seminar = make_seminar(capacity=50)
		register_many(seminar, 3)
		self.assertEqual(page_tickets(seminar)["General"]["remaining"], 47)

	def test_settings_threshold_applies_to_the_page(self):
		set_settings("Threshold", 10)
		seminar = make_seminar(capacity=50)
		register_many(seminar, 3)
		ticket = page_tickets(seminar)["General"]
		self.assertIsNone(ticket["remaining"])
		self.assertEqual(ticket["label"], "Seats available")

	def test_seminar_and_ticket_overrides(self):
		seminar = make_seminar(
			capacity=50,
			seat_display="Threshold",
			seat_display_threshold=48,
			tickets=[
				{"ticket_name": "General", "price": 0, "currency": "JPY", "enabled": 1},
				{"ticket_name": "VIP", "price": 0, "currency": "JPY", "enabled": 1, "seat_display": "Hidden"},
				{
					"ticket_name": "Small",
					"price": 0,
					"currency": "JPY",
					"enabled": 1,
					"capacity": 5,
					"seat_display_threshold": 3,
				},
			],
		)
		register_many(seminar, 3)
		tickets = page_tickets(seminar)
		self.assertEqual(tickets["General"]["remaining"], 47)  # 47 <= seminar threshold 48
		self.assertIsNone(tickets["VIP"]["remaining"])  # ticket: Hidden
		self.assertIsNone(tickets["Small"]["remaining"])  # 5 left > ticket threshold 3
		self.assertEqual(tickets["Small"]["label"], "Seats available")

	def test_sold_out_ticket_still_closes_registration(self):
		set_settings("Hidden")
		seminar = make_seminar(capacity=2)
		register_many(seminar, 2)
		self.assertTrue(page_tickets(seminar)["General"]["sold_out"])
