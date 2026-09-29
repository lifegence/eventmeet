"""Scheduled jobs (see hooks.scheduler_events)."""

import frappe
from frappe.utils import add_to_date, cint, now_datetime

from eventmeet.services import conference, notifications, registration, stripe_api

BATCH_SIZE = 100


def _each(names, fn, title: str):
	for name in names:
		try:
			fn(name)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"{title} failed for {name}", message=frappe.get_traceback())


def reconcile_pending_payments():
	"""Fallback for missed Stripe webhooks: ask Stripe for the checkout state."""
	expiry = cint(frappe.db.get_single_value("Seminar Settings", "checkout_expiry_minutes")) or 30
	names = frappe.get_all(
		"Seminar Registration",
		filters={
			"status": "Pending Payment",
			"stripe_checkout_session": ["is", "set"],
			"creation": ["<", add_to_date(now_datetime(), minutes=-(expiry + 5))],
		},
		pluck="name",
		order_by="creation asc",
		limit=BATCH_SIZE,
	)

	def reconcile(name):
		checkout_id = frappe.db.get_value("Seminar Registration", name, "stripe_checkout_session")
		checkout = stripe_api.retrieve_checkout_session(checkout_id)
		if checkout.get("status") == "expired":
			registration.handle_checkout_event("checkout.session.expired", checkout)
		elif checkout.get("status") == "complete":
			registration.handle_checkout_event("checkout.session.completed", checkout)

	_each(names, reconcile, "Payment reconciliation")


def retry_missing_conference_registrations():
	rows = frappe.db.sql(
		"""
		select r.name
		from `tabSeminar Registration` r
		join `tabSeminar` s on s.name = r.seminar
		where r.status = 'Confirmed'
			and ifnull(r.join_url, '') = ''
			and s.format in ('Online', 'Hybrid')
			and ifnull(s.conference_session, '') != ''
			and s.ends_at > %(now)s
		limit %(limit)s
		""",
		{"now": now_datetime(), "limit": BATCH_SIZE},
		pluck=True,
	)

	def retry(name):
		doc = frappe.get_doc("Seminar Registration", name)
		if registration.ensure_conference_registration(doc) and doc.join_url:
			notifications.send_registration_confirmed(doc)

	_each(rows, retry, "Conference registration retry")


def process_ended_conference_sessions():
	conference.process_ended_sessions()


def send_seminar_reminders():
	hours = cint(frappe.db.get_single_value("Seminar Settings", "reminder_hours_before"))
	if hours <= 0:
		return
	now = now_datetime()
	seminars = frappe.get_all(
		"Seminar",
		filters={
			"status": ["in", ["Open", "Closed"]],
			"starts_at": ["between", [now, add_to_date(now, hours=hours)]],
		},
		pluck="name",
	)
	for seminar in seminars:
		names = frappe.get_all(
			"Seminar Registration",
			filters={"seminar": seminar, "status": "Confirmed", "reminder_sent": 0},
			pluck="name",
			limit=500,
		)

		def remind(name):
			doc = frappe.get_doc("Seminar Registration", name)
			if notifications.send_seminar_reminder(doc):
				doc.db_set("reminder_sent", 1, update_modified=False)

		_each(names, remind, "Seminar reminder")


def send_feedback_requests():
	now = now_datetime()
	frappe.db.sql(
		"update `tabSeminar` set status = 'Completed' where status in ('Open', 'Closed') and ends_at < %(now)s",
		{"now": now},
	)
	frappe.db.commit()

	if not cint(frappe.db.get_single_value("Seminar Settings", "send_feedback_request")):
		return
	# Only recent seminars: do not send surprise requests for old events.
	seminars = frappe.get_all(
		"Seminar",
		filters={
			"status": "Completed",
			"feedback_enabled": 1,
			"ends_at": ["between", [add_to_date(now, days=-3), now]],
		},
		pluck="name",
	)
	for seminar in seminars:
		names = frappe.get_all(
			"Seminar Registration",
			filters={"seminar": seminar, "status": "Confirmed", "feedback_requested": 0},
			pluck="name",
			limit=1000,
		)

		def request_feedback(name):
			doc = frappe.get_doc("Seminar Registration", name)
			if notifications.send_feedback_request(doc):
				doc.db_set("feedback_requested", 1, update_modified=False)

		_each(names, request_feedback, "Feedback request")
