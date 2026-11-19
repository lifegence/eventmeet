"""Registration form questions, the join information schedule and reminders."""

from unittest.mock import patch

import frappe
from frappe.utils import add_to_date, now_datetime

from eventmeet import tasks
from eventmeet.api import public
from eventmeet.services import registration as reg_service
from eventmeet.tests.test_pages import render
from eventmeet.tests.utils import (
	SeminarTestCase,
	capture_mail,
	make_host,
	make_seminar,
	patch_providers,
	reset_conference_sessions,
)


def registration_for(seminar, email="alice@example.com"):
	return frappe.get_last_doc("Seminar Registration", filters={"seminar": seminar.name, "email": email})


def keep_in_test_transaction(testcase):
	"""The scheduled jobs commit after each registration; keep the test data in the test's transaction."""
	for target in ("frappe.db.commit", "frappe.db.rollback"):
		patcher = patch(target)
		patcher.start()
		testcase.addCleanup(patcher.stop)


def set_settings(testcase, **values):
	settings = frappe.get_doc("Seminar Settings")
	previous = {key: settings.get(key) for key in values}
	settings.update(values)
	settings.save(ignore_permissions=True)

	def restore():
		settings = frappe.get_doc("Seminar Settings")
		settings.update(previous)
		settings.save(ignore_permissions=True)

	testcase.addCleanup(restore)


class TestRegistrationForm(SeminarTestCase):
	def setUp(self):
		self.mail = capture_mail(self)

	def register(self, seminar, email="alice@example.com", company="ACME", phone="03-0000-0000", **answers):
		return reg_service.create_registration(
			seminar.name, "General", "Alice", email, company, phone, answers=answers
		)

	def test_company_can_be_required(self):
		seminar = make_seminar(require_company=1)
		with self.assertRaises(frappe.ValidationError):
			self.register(seminar, company=" ")
		self.register(seminar, company="ACME")
		self.assertEqual(registration_for(seminar).company, "ACME")

	def test_phone_is_dropped_when_not_asked(self):
		seminar = make_seminar(ask_phone=0)
		self.register(seminar)
		self.assertFalse(registration_for(seminar).phone)

	def test_only_asked_questions_are_stored(self):
		seminar = make_seminar(
			ask_department=1,
			ask_question=1,
			ask_consultation=1,
			interest_options="ERP\nGroupware\nAI agents\n\nERP",
		)
		self.register(
			seminar,
			department="IT",
			job_title="Manager",
			interests="AI agents\nERP\nNot an option",
			question="How do approvals work?",
			consultation_requested="1",
			marketing_opt_in="1",
		)
		doc = registration_for(seminar)
		self.assertEqual((doc.department, doc.job_title), ("IT", "Manager"))
		self.assertEqual(doc.interests, "ERP\nAI agents", "options order, unknown topics dropped")
		self.assertEqual(doc.question, "How do approvals work?")
		self.assertEqual(doc.consultation_requested, 1)
		self.assertEqual(doc.marketing_opt_in, 0, "not asked in the settings")

		plain = make_seminar(title="Plain")
		self.register(plain, department="IT", question="?", consultation_requested="1", interests=["ERP"])
		doc = registration_for(plain)
		self.assertFalse(doc.department or doc.question or doc.interests)
		self.assertEqual(doc.consultation_requested, 0)

	def test_privacy_consent_and_marketing_opt_in(self):
		set_settings(self, require_privacy_consent=1, ask_marketing_opt_in=1)
		seminar = make_seminar()
		with self.assertRaises(frappe.ValidationError):
			self.register(seminar)
		self.register(seminar, privacy_consent="on")
		doc = registration_for(seminar)
		self.assertTrue(doc.privacy_consent_at)
		self.assertEqual(doc.marketing_opt_in, 0, "unchecked unless the registrant opts in")

		self.register(seminar, email="bob@example.com", privacy_consent="1", marketing_opt_in="true")
		self.assertEqual(registration_for(seminar, "bob@example.com").marketing_opt_in, 1)

	def test_public_endpoint_passes_the_answers_through(self):
		seminar = make_seminar(ask_department=1, interest_options="ERP\nAI agents")
		# Outside a web request the endpoint's rate limit does not apply (render() leaves one behind).
		frappe.local.request = None
		public.register(
			seminar=seminar.name,
			ticket_type="General",
			attendee_name="Bob",
			email="bob@example.com",
			department="Sales",
			interests="ERP\nAI agents",
		)
		doc = registration_for(seminar, "bob@example.com")
		self.assertEqual(doc.department, "Sales")
		self.assertEqual(doc.interests, "ERP\nAI agents")

	def test_form_shows_the_configured_questions(self):
		set_settings(
			self,
			require_privacy_consent=1,
			privacy_policy_url="https://example.com/privacy",
			ask_marketing_opt_in=1,
		)
		seminar = make_seminar(
			require_company=1, ask_phone=0, ask_department=1, ask_consultation=1, interest_options="ERP"
		)
		status, html = render(seminar.route)
		self.assertEqual(status, 200)
		for name in (
			'name="department"',
			'name="interests"',
			'name="consultation_requested"',
			'name="privacy_consent"',
			'name="marketing_opt_in"',
			"https://example.com/privacy",
		):
			self.assertIn(name, html)
		self.assertNotIn('name="phone"', html)
		self.assertNotIn('name="question"', html)
		self.assertNotIn('name="marketing_opt_in" value="1" checked', html)


class TestJoinInformation(SeminarTestCase):
	def setUp(self):
		frappe.db.set_single_value("Conferencing Settings", "allocation_buffer_minutes", 15)
		reset_conference_sessions()
		self.mail = capture_mail(self)
		keep_in_test_transaction(self)
		make_host("Seminar Host", meeting_capacity=100, webinar_capacity=500)
		self.fakes = patch_providers(self)

	def register(self, seminar, email="alice@example.com"):
		return reg_service.create_registration(seminar.name, "General", "Alice", email)

	def test_without_a_send_time_the_confirmation_includes_the_link(self):
		seminar = make_seminar(fmt="Online")
		self.register(seminar)
		doc = registration_for(seminar)
		self.assertIn(doc.join_url, self.mail[-1]["rendered"])
		self.assertEqual(doc.join_info_sent, 1)

	def test_link_is_sent_at_the_send_time_and_with_later_confirmations(self):
		send_at = add_to_date(now_datetime(), days=2)
		seminar = make_seminar(fmt="Online", join_info_send_at=send_at, joining_instructions="Use Chrome.")
		self.register(seminar)
		doc = registration_for(seminar)
		confirmation = self.mail[-1]["rendered"]
		self.assertNotIn(doc.join_url, confirmation)
		self.assertIn(frappe.utils.format_datetime(send_at, "yyyy-MM-dd HH:mm"), confirmation)
		self.assertEqual(doc.join_info_sent, 0)

		status, html = render("seminar-registration", token=doc.access_token)
		self.assertEqual(status, 200)
		self.assertNotIn(doc.join_url, html, "the thanks page does not show the link early")

		tasks.send_join_information()
		self.assertEqual(len(self.mail), 1, "not due yet")

		frappe.db.set_value(
			"Seminar", seminar.name, "join_info_send_at", add_to_date(now_datetime(), minutes=-1)
		)
		tasks.send_join_information()
		self.assertEqual(len(self.mail), 2)
		self.assertIn("Join information", self.mail[-1]["subject"])
		self.assertIn(doc.join_url, self.mail[-1]["rendered"])
		self.assertIn("Use Chrome.", self.mail[-1]["rendered"])
		self.assertEqual(registration_for(seminar).join_info_sent, 1)

		tasks.send_join_information()
		self.assertEqual(len(self.mail), 2, "sent once")

		# A registrant after the send time gets the link with the confirmation, not a second email.
		self.register(seminar, email="late@example.com")
		late = registration_for(seminar, "late@example.com")
		self.assertIn(late.join_url, self.mail[-1]["rendered"])
		self.assertEqual(late.join_info_sent, 1)
		tasks.send_join_information()
		self.assertEqual(len(self.mail), 3)

		status, html = render("seminar-registration", token=late.access_token)
		self.assertIn(late.join_url, html)

	def test_retried_zoom_registration_sends_the_link_only_when_due(self):
		seminar = make_seminar(fmt="Online", join_info_send_at=add_to_date(now_datetime(), days=1))
		self.register(seminar)
		doc = registration_for(seminar)
		doc.db_set({"join_url": "", "conference_registrant_id": ""})  # as if Zoom had failed
		sent = len(self.mail)
		tasks.retry_missing_conference_registrations()
		self.assertTrue(registration_for(seminar).join_url)
		self.assertEqual(len(self.mail), sent, "not due: send_join_information sends it later")

		frappe.db.set_value(
			"Seminar", seminar.name, "join_info_send_at", add_to_date(now_datetime(), minutes=-1)
		)
		registration_for(seminar).db_set("join_url", "")
		tasks.retry_missing_conference_registrations()
		self.assertEqual(len(self.mail), sent + 1)
		self.assertIn("Join information", self.mail[-1]["subject"])
		self.assertEqual(registration_for(seminar).join_info_sent, 1)

	def test_own_join_url_for_everyone(self):
		seminar = make_seminar(fmt="Online", use_own_join_url=1, own_join_url="https://meet.example.com/abc")
		self.assertFalse(seminar.conference_session, "no Zoom session")
		self.assertFalse(self.fakes["Zoom"].called("create"))
		self.register(seminar)
		self.register(seminar, email="bob@example.com")
		doc = registration_for(seminar)
		self.assertFalse(doc.join_url)
		self.assertIn("https://meet.example.com/abc", self.mail[-1]["rendered"])
		self.assertNotIn("personal link", self.mail[-1]["rendered"])
		self.assertEqual(doc.join_info_sent, 1)

	def test_switching_to_own_url_cancels_the_zoom_session(self):
		seminar = make_seminar(fmt="Online")
		session = seminar.conference_session
		seminar.use_own_join_url = 1
		seminar.own_join_url = "https://meet.example.com/abc"
		seminar.save()
		self.assertEqual(frappe.db.get_value("Conference Session", session, "status"), "Cancelled")

	def test_validation(self):
		seminar = make_seminar(fmt="Online")
		seminar.join_info_send_at = add_to_date(seminar.starts_at, minutes=1)
		with self.assertRaises(frappe.ValidationError):
			seminar.save()
		seminar.reload()
		seminar.use_own_join_url = 1
		seminar.own_join_url = "javascript:alert(1)"
		with self.assertRaises(frappe.ValidationError):
			seminar.save()


class TestReminders(SeminarTestCase):
	def setUp(self):
		self.mail = capture_mail(self)
		keep_in_test_transaction(self)
		set_settings(self, reminder_hours_before=24)

	def test_seminar_hours_override_the_settings(self):
		seminar = make_seminar(
			fmt="Online",
			use_own_join_url=1,
			own_join_url="https://meet.example.com/abc",
			reminder_hours_before=2,
			starts_at=add_to_date(now_datetime(), hours=3),
		)
		reg_service.create_registration(seminar.name, "General", "Alice", "alice@example.com")
		sent = len(self.mail)
		tasks.send_seminar_reminders()
		self.assertEqual(len(self.mail), sent, "3 hours before: not yet")

		frappe.db.set_value("Seminar", seminar.name, "starts_at", add_to_date(now_datetime(), minutes=100))
		tasks.send_seminar_reminders()
		self.assertEqual(len(self.mail), sent + 1)
		self.assertIn("Reminder", self.mail[-1]["subject"])
		self.assertIn("https://meet.example.com/abc", self.mail[-1]["rendered"])
		tasks.send_seminar_reminders()
		self.assertEqual(len(self.mail), sent + 1, "sent once")

	def test_settings_hours_apply_by_default(self):
		seminar = make_seminar(starts_at=add_to_date(now_datetime(), hours=20))
		reg_service.create_registration(seminar.name, "General", "Alice", "alice@example.com")
		sent = len(self.mail)
		tasks.send_seminar_reminders()
		self.assertEqual(len(self.mail), sent + 1)
