from unittest.mock import patch

import frappe
from frappe.utils import add_to_date, now_datetime

from eventmeet.services import registration as reg_service
from eventmeet.services import stripe_api
from eventmeet.tests.utils import (
	SeminarTestCase,
	capture_mail,
	make_host,
	make_seminar,
	patch_providers,
	reset_conference_sessions,
)

PAID_TICKETS = [
	{"ticket_name": "Standard", "price": 5500, "currency": "JPY", "enabled": 1},
	{"ticket_name": "Free", "price": 0, "currency": "JPY", "enabled": 1, "capacity": 1},
]


def register(seminar, ticket="General", email="alice@example.com", name="Alice"):
	return reg_service.create_registration(seminar.name, ticket, name, email, "ACME", "03-0000-0000")


def registration_for(seminar, email="alice@example.com"):
	return frappe.get_last_doc("Seminar Registration", filters={"seminar": seminar.name, "email": email})


class TestFreeRegistration(SeminarTestCase):
	def setUp(self):
		self.mail = capture_mail(self)

	def test_default_deadline_follows_the_start_time(self):
		seminar = make_seminar()
		self.assertEqual(seminar.registration_closes_at, seminar.starts_at)
		seminar.starts_at = add_to_date(seminar.starts_at, hours=1)
		seminar.ends_at = add_to_date(seminar.ends_at, hours=1)
		seminar.save(ignore_permissions=True)
		self.assertEqual(seminar.registration_closes_at, seminar.starts_at)

		deadline = add_to_date(seminar.starts_at, days=-1)
		seminar.registration_closes_at = deadline
		seminar.save(ignore_permissions=True)
		seminar.starts_at = add_to_date(seminar.starts_at, hours=1)
		seminar.ends_at = add_to_date(seminar.ends_at, hours=1)
		seminar.save(ignore_permissions=True)
		self.assertEqual(seminar.registration_closes_at, deadline, "an edited deadline is kept")

	def test_free_registration_is_confirmed_immediately(self):
		seminar = make_seminar()
		result = register(seminar)
		self.assertEqual(result["status"], "Confirmed")
		doc = registration_for(seminar)
		self.assertEqual(doc.status, "Confirmed")
		self.assertIn(doc.access_token, result["redirect_url"])
		self.assertEqual(len(self.mail), 1)
		self.assertEqual(self.mail[0]["recipients"], ["alice@example.com"])
		self.assertEqual(self.mail[0]["attachments"][0]["fname"], "checkin-qr.png")
		self.assertIn(doc.access_token, self.mail[0]["rendered"])

	def test_email_is_normalized_and_duplicates_rejected(self):
		seminar = make_seminar()
		register(seminar, email="  Bob@Example.COM ")
		self.assertEqual(registration_for(seminar, "bob@example.com").email, "bob@example.com")
		with self.assertRaises(frappe.ValidationError):
			register(seminar, email="bob@example.com")

	def test_capacity_is_enforced(self):
		seminar = make_seminar(capacity=1)
		register(seminar, email="one@example.com")
		with self.assertRaises(frappe.ValidationError):
			register(seminar, email="two@example.com")

	def test_ticket_capacity_is_enforced(self):
		seminar = make_seminar(tickets=PAID_TICKETS)
		register(seminar, ticket="Free", email="one@example.com")
		with self.assertRaises(frappe.ValidationError):
			register(seminar, ticket="Free", email="two@example.com")

	def test_closed_draft_or_unpublished_seminar_rejects(self):
		for kwargs in (
			{"status": "Draft"},
			{"published": 0},
			{"registration_closes_at": add_to_date(now_datetime(), days=-1)},
		):
			seminar = make_seminar(**kwargs)
			with self.assertRaises(frappe.ValidationError):
				register(seminar)

	def test_unknown_ticket_rejected(self):
		seminar = make_seminar()
		with self.assertRaises(frappe.ValidationError):
			register(seminar, ticket="VIP")

	def test_invalid_email_rejected(self):
		seminar = make_seminar()
		with self.assertRaises(frappe.ValidationError):
			register(seminar, email="not-an-email")


class TestPaidRegistration(SeminarTestCase):
	def setUp(self):
		self.mail = capture_mail(self)
		self.seminar = make_seminar(tickets=PAID_TICKETS)
		self.stripe_calls = []

		def fake_request(method, path, data=None, idempotency_key=None):
			self.stripe_calls.append((method, path, data))
			if path == "/checkout/sessions":
				return {"id": "cs_test_1", "url": "https://checkout.stripe.test/cs_test_1"}
			if path == "/refunds":
				return {"id": "re_1", "amount": data.get("amount", 5500)}
			return {}

		patcher = patch.object(stripe_api, "_request", side_effect=fake_request)
		patcher.start()
		self.addCleanup(patcher.stop)

	def checkout_payload(self, **overrides):
		doc = registration_for(self.seminar)
		payload = {
			"id": doc.stripe_checkout_session,
			"client_reference_id": doc.name,
			"payment_status": "paid",
			"amount_total": 5500,
			"currency": "jpy",
			"payment_intent": "pi_1",
		}
		payload.update(overrides)
		return payload

	def test_paid_registration_starts_checkout(self):
		result = register(self.seminar, ticket="Standard")
		self.assertEqual(result["redirect_url"], "https://checkout.stripe.test/cs_test_1")
		doc = registration_for(self.seminar)
		self.assertEqual((doc.status, doc.amount, doc.currency), ("Pending Payment", 5500, "JPY"))
		self.assertEqual(doc.stripe_checkout_session, "cs_test_1")
		_method, _path, data = self.stripe_calls[0]
		self.assertEqual(data["line_items[0][price_data][unit_amount]"], 5500)
		self.assertEqual(data["line_items[0][price_data][currency]"], "jpy")
		self.assertEqual(data["client_reference_id"], doc.name)

	def test_completed_checkout_confirms_once(self):
		register(self.seminar, ticket="Standard")
		reg_service.handle_checkout_event("checkout.session.completed", self.checkout_payload())
		reg_service.handle_checkout_event("checkout.session.completed", self.checkout_payload())
		doc = registration_for(self.seminar)
		self.assertEqual((doc.status, doc.stripe_payment_intent), ("Confirmed", "pi_1"))
		self.assertTrue(doc.paid_at)
		self.assertEqual(len(self.mail), 1, "confirmation email is sent exactly once")

	def test_amount_mismatch_does_not_confirm(self):
		register(self.seminar, ticket="Standard")
		reg_service.handle_checkout_event("checkout.session.completed", self.checkout_payload(amount_total=1))
		self.assertEqual(registration_for(self.seminar).status, "Pending Payment")

	def test_async_payment_waits_then_confirms(self):
		register(self.seminar, ticket="Standard")
		reg_service.handle_checkout_event(
			"checkout.session.completed", self.checkout_payload(payment_status="unpaid")
		)
		self.assertEqual(registration_for(self.seminar).status, "Pending Payment")
		reg_service.handle_checkout_event("checkout.session.async_payment_succeeded", self.checkout_payload())
		self.assertEqual(registration_for(self.seminar).status, "Confirmed")

	def test_expired_checkout_releases_seat(self):
		register(self.seminar, ticket="Standard")
		reg_service.handle_checkout_event("checkout.session.expired", self.checkout_payload())
		self.assertEqual(registration_for(self.seminar).status, "Expired")
		self.assertEqual(reg_service.count_active(self.seminar.name), 0)

	def test_event_for_other_checkout_is_ignored(self):
		register(self.seminar, ticket="Standard")
		reg_service.handle_checkout_event("checkout.session.completed", self.checkout_payload(id="cs_other"))
		self.assertEqual(registration_for(self.seminar).status, "Pending Payment")

	def test_retry_replaces_previous_pending_registration(self):
		register(self.seminar, ticket="Standard")
		first = registration_for(self.seminar).name
		register(self.seminar, ticket="Standard")
		self.assertEqual(frappe.db.get_value("Seminar Registration", first, "status"), "Expired")
		self.assertIn(("POST", "/checkout/sessions/cs_test_1/expire", None), self.stripe_calls)

	def test_refund(self):
		register(self.seminar, ticket="Standard")
		reg_service.handle_checkout_event("checkout.session.completed", self.checkout_payload())
		doc = reg_service.cancel_registration(registration_for(self.seminar).name, refund=True)
		self.assertEqual((doc.status, doc.refunded_amount), ("Refunded", 5500))
		self.assertEqual(self.stripe_calls[-1][2]["payment_intent"], "pi_1")

	def test_manual_confirmation(self):
		register(self.seminar, ticket="Standard")
		doc = reg_service.confirm_manually(registration_for(self.seminar).name)
		self.assertEqual(doc.status, "Confirmed")
		self.assertFalse(doc.paid_at)


class TestCheckInAndFeedback(SeminarTestCase):
	def setUp(self):
		self.mail = capture_mail(self)

	def test_check_in_is_idempotent(self):
		seminar = make_seminar()
		register(seminar)
		token = registration_for(seminar).access_token
		self.assertFalse(reg_service.check_in(token)["already_checked_in"])
		self.assertTrue(reg_service.check_in(token)["already_checked_in"])
		with self.assertRaises(frappe.DoesNotExistError):
			reg_service.check_in("x" * 40)

	def test_feedback_only_after_start_and_once(self):
		seminar = make_seminar()
		register(seminar)
		token = registration_for(seminar).access_token
		with self.assertRaises(frappe.ValidationError):
			reg_service.submit_feedback(token, 5)

		frappe.db.set_value("Seminar", seminar.name, "starts_at", add_to_date(now_datetime(), hours=-1))
		reg_service.submit_feedback(token, 4, "Good", 1)
		feedback = frappe.get_last_doc("Seminar Feedback", filters={"seminar": seminar.name})
		self.assertAlmostEqual(feedback.rating, 0.8)
		with self.assertRaises(frappe.ValidationError):
			reg_service.submit_feedback(token, 5)

	def test_feedback_rating_range(self):
		seminar = make_seminar()
		register(seminar)
		frappe.db.set_value("Seminar", seminar.name, "starts_at", add_to_date(now_datetime(), hours=-1))
		with self.assertRaises(frappe.ValidationError):
			reg_service.submit_feedback(registration_for(seminar).access_token, 9)


class TestOnlineSeminar(SeminarTestCase):
	def setUp(self):
		frappe.db.set_single_value("Conferencing Settings", "allocation_buffer_minutes", 15)
		reset_conference_sessions()
		self.mail = capture_mail(self)
		make_host("Seminar Host", meeting_capacity=100, webinar_capacity=500)
		self.fakes = patch_providers(self)
		self.provider = self.fakes["Zoom"]

	def test_opening_online_seminar_creates_session_and_registers_attendee(self):
		seminar = make_seminar(fmt="Online", status="Draft", conference_kind="Webinar", capacity=200)
		self.assertFalse(seminar.conference_session)

		seminar.status = "Open"
		seminar.save()
		seminar.reload()
		self.assertTrue(seminar.conference_session)
		session = frappe.get_doc("Conference Session", seminar.conference_session)
		self.assertEqual(
			(session.kind, session.host_account, session.registration_required),
			("Webinar", "Seminar Host", 1),
		)

		register(seminar)
		doc = registration_for(seminar)
		self.assertTrue(doc.join_url.startswith("https://zoom.test/w/"))
		self.assertIn(doc.join_url, self.mail[-1]["rendered"])
		self.assertFalse(self.mail[-1]["attachments"], "online-only seminars have no check-in QR")
		self.assertEqual(doc.conference_registrant_id, "r-alice@example.com")

	def test_reschedule_and_cancel(self):
		seminar = make_seminar(fmt="Hybrid", conference_kind="Meeting")
		seminar.starts_at = add_to_date(seminar.starts_at, hours=1)
		seminar.ends_at = add_to_date(seminar.ends_at, hours=1)
		seminar.save()
		self.assertEqual(len(self.provider.called("update")), 1)

		register(seminar)
		seminar.reload()
		seminar.status = "Cancelled"
		seminar.save()
		self.assertEqual(
			frappe.db.get_value("Conference Session", seminar.conference_session, "status"), "Cancelled"
		)
		self.assertEqual(len(self.provider.called("delete")), 1)

	def test_cancel_registration_cancels_zoom_registrant(self):
		seminar = make_seminar(fmt="Online")
		register(seminar)
		reg_service.cancel_registration(registration_for(seminar).name)
		self.assertEqual(len(self.provider.called("cancel_registrant")), 1)
		self.assertFalse(registration_for(seminar).join_url)
		self.assertIn("Registration cancelled", self.mail[-1]["subject"])

	def test_attendance_is_applied_to_registrations(self):
		from eventmeet.conferencing.providers import ParticipantRecord
		from eventmeet.services import conference

		seminar = make_seminar(fmt="Online")
		register(seminar, email="alice@example.com")
		register(seminar, email="bob@example.com", name="Bob")
		self.provider.participants = [
			ParticipantRecord("Alice", "alice@example.com", None, None, 30),
			ParticipantRecord("Alice", "alice@example.com", None, None, 15.5),
		]
		seminar.reload()
		conference.sync_attendance(seminar.conference_session)
		alice, bob = (
			registration_for(seminar, "alice@example.com"),
			registration_for(seminar, "bob@example.com"),
		)
		self.assertEqual((alice.attended_online, alice.online_minutes), (1, 45.5))
		self.assertEqual(bob.attended_online, 0)
		self.assertEqual(
			frappe.db.get_value("Conference Session", seminar.conference_session, "status"), "Ended"
		)
