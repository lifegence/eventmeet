"""Seminar registration lifecycle: register → pay (Stripe) → confirm → online seat (Zoom)."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import (
	cint,
	flt,
	get_datetime,
	get_url,
	now_datetime,
	strip_html,
	validate_email_address,
)

from lifegence_seminar.services import notifications, stripe_api
from lifegence_seminar.services.conference import cancel_participant, register_participant

ACTIVE_STATUSES = ("Pending Payment", "Confirmed")


def status_url(registration) -> str:
	return get_url(f"/seminar-registration?token={registration.access_token}")


def checkin_url(registration) -> str:
	return get_url(f"/seminar-checkin?token={registration.access_token}")


def feedback_url(registration) -> str:
	return get_url(f"/seminar-feedback?token={registration.access_token}")


def get_registration_by_token(token: str | None, for_update: bool = False):
	if not token or len(token) < 20:
		return None
	name = frappe.db.get_value("Seminar Registration", {"access_token": token}, "name")
	if not name:
		return None
	return frappe.get_doc("Seminar Registration", name, for_update=for_update)


def count_active(seminar: str, ticket_type: str | None = None) -> int:
	filters = {"seminar": seminar, "status": ["in", ACTIVE_STATUSES]}
	if ticket_type:
		filters["ticket_type"] = ticket_type
	return frappe.db.count("Seminar Registration", filters)


def _clean_text(value: str | None, label: str, max_length: int, required: bool = False) -> str:
	# Plain-text fields: drop markup so the stored value is never HTML-sanitized/entity-encoded.
	value = strip_html(value or "").strip()
	if required and not value:
		frappe.throw(_("{0} is required.").format(_(label)))
	if len(value) > max_length:
		frappe.throw(_("{0} is too long.").format(_(label)))
	return value


def create_registration(
	seminar: str,
	ticket_type: str,
	attendee_name: str,
	email: str,
	company: str | None = None,
	phone: str | None = None,
) -> dict:
	attendee_name = _clean_text(attendee_name, "Attendee Name", 140, required=True)
	email = validate_email_address(_clean_text(email, "Email", 140, required=True), throw=True).lower()
	company = _clean_text(company, "Company", 140)
	phone = _clean_text(phone, "Phone", 40)

	# Lock the seminar row: capacity checks below must not race with parallel registrations.
	if not frappe.db.get_value("Seminar", seminar, "name", for_update=True):
		frappe.throw(_("Seminar not found."), frappe.DoesNotExistError)
	seminar_doc = frappe.get_doc("Seminar", seminar)
	seminar_doc.validate_open_for_registration()
	ticket = seminar_doc.get_ticket(ticket_type)

	_release_previous_pending(seminar, email)
	if frappe.db.exists("Seminar Registration", {"seminar": seminar, "email": email, "status": "Confirmed"}):
		frappe.throw(_("This email address is already registered for this seminar."))

	if cint(seminar_doc.capacity) and count_active(seminar) >= cint(seminar_doc.capacity):
		frappe.throw(_("This seminar is fully booked."))
	if cint(ticket.capacity) and count_active(seminar, ticket.ticket_name) >= cint(ticket.capacity):
		frappe.throw(_("Ticket {0} is sold out.").format(ticket.ticket_name))

	registration = frappe.get_doc(
		{
			"doctype": "Seminar Registration",
			"seminar": seminar,
			"ticket_type": ticket.ticket_name,
			"attendee_name": attendee_name,
			"email": email,
			"company": company,
			"phone": phone,
			"status": "Pending Payment",
			"amount": flt(ticket.price),
			"currency": ticket.currency or seminar_doc.get_default_currency(),
			"access_token": frappe.generate_hash(length=40),
		}
	)
	# Guest path: authorization is the published/open seminar check above + rate limit on the endpoint.
	registration.insert(ignore_permissions=True)

	if flt(registration.amount) <= 0:
		confirm_registration(registration.name)
		return {"status": "Confirmed", "redirect_url": status_url(registration)}

	settings = frappe.get_single("Seminar Settings")
	try:
		checkout = stripe_api.create_checkout_session(
			registration=registration.name,
			product_name=f"{seminar_doc.title} - {ticket.ticket_name}",
			amount=registration.amount,
			currency=registration.currency,
			customer_email=email,
			success_url=status_url(registration) + "&checkout=success",
			cancel_url=status_url(registration) + "&checkout=cancelled",
			expires_in_minutes=cint(settings.checkout_expiry_minutes) or 30,
			create_invoice=bool(settings.stripe_create_invoice),
		)
	except stripe_api.StripeError:
		frappe.log_error(title="Stripe checkout creation failed", message=frappe.get_traceback())
		frappe.throw(_("Payment could not be started. Please try again later."))

	registration.db_set("stripe_checkout_session", checkout["id"])
	return {"status": "Pending Payment", "redirect_url": checkout["url"]}


def _release_previous_pending(seminar: str, email: str) -> None:
	"""A retried registration replaces an unfinished checkout of the same person."""
	for name in frappe.get_all(
		"Seminar Registration",
		filters={"seminar": seminar, "email": email, "status": "Pending Payment"},
		pluck="name",
	):
		expire_registration(name, expire_checkout=True)


def confirm_registration(name: str, payment_intent: str | None = None):
	registration = frappe.get_doc("Seminar Registration", name, for_update=True)
	if registration.status == "Confirmed":
		return registration
	if registration.status in ("Cancelled", "Refunded"):
		frappe.log_error(
			title="Payment received for inactive registration",
			message=f"{name} is {registration.status}; payment_intent={payment_intent}. Refund manually if needed.",
		)
		return registration

	registration.status = "Confirmed"
	if payment_intent:
		# Manual confirmations (invoice / bank transfer) record no payment time here.
		registration.stripe_payment_intent = payment_intent
		registration.paid_at = now_datetime()
	registration.save(ignore_permissions=True)

	ensure_conference_registration(registration)
	notifications.send_registration_confirmed(registration)
	return registration


def confirm_manually(name: str):
	"""Confirm without online payment (invoice / bank transfer / invited guest)."""
	registration = frappe.get_doc("Seminar Registration", name)
	if registration.status != "Pending Payment":
		frappe.throw(_("Only pending registrations can be confirmed."))
	if registration.stripe_checkout_session:
		try:
			stripe_api.expire_checkout_session(registration.stripe_checkout_session)
		except stripe_api.StripeError:
			frappe.logger("lifegence_seminar").warning(f"Could not expire checkout for {name}")
	return confirm_registration(name)


def ensure_conference_registration(registration) -> bool:
	"""Register the attendee on the online session. Failures are retried by the scheduler."""
	if registration.status != "Confirmed" or registration.join_url:
		return True
	seminar = frappe.db.get_value(
		"Seminar", registration.seminar, ["format", "conference_session"], as_dict=True
	)
	if not seminar or seminar.format == "Offline" or not seminar.conference_session:
		return True
	try:
		registrant_id, join_url = register_participant(
			seminar.conference_session, registration.email, registration.attendee_name
		)
	except Exception:
		frappe.log_error(title="Conference registration failed", message=frappe.get_traceback())
		return False
	registration.db_set({"conference_registrant_id": registrant_id, "join_url": join_url})
	return True


def expire_registration(name: str, expire_checkout: bool = False) -> None:
	registration = frappe.get_doc("Seminar Registration", name, for_update=True)
	if registration.status != "Pending Payment":
		return
	if expire_checkout and registration.stripe_checkout_session:
		try:
			stripe_api.expire_checkout_session(registration.stripe_checkout_session)
		except stripe_api.StripeError:
			# Already expired/completed sessions cannot be expired again; the webhook decides the final state.
			frappe.logger("lifegence_seminar").warning(f"Could not expire checkout for {name}")
	registration.status = "Expired"
	registration.save(ignore_permissions=True)


def cancel_registration(name: str, refund: bool = False, notify: bool = True):
	registration = frappe.get_doc("Seminar Registration", name, for_update=True)
	if registration.status in ("Cancelled", "Refunded", "Expired"):
		return registration

	if registration.status == "Pending Payment":
		expire_registration(name, expire_checkout=True)
		return frappe.get_doc("Seminar Registration", name)

	new_status = "Cancelled"
	if refund and flt(registration.amount) > 0:
		if not registration.stripe_payment_intent:
			frappe.throw(_("No Stripe payment is linked to this registration; refund it manually."))
		try:
			result = stripe_api.create_refund(
				payment_intent=registration.stripe_payment_intent, registration=registration.name
			)
		except stripe_api.StripeError as e:
			frappe.log_error(title="Stripe refund failed", message=frappe.get_traceback())
			frappe.throw(_("Refund failed: {0}").format(e))
		registration.refunded_amount = stripe_api.from_minor_units(
			result.get("amount", 0), registration.currency
		)
		new_status = "Refunded"

	session = frappe.db.get_value("Seminar", registration.seminar, "conference_session")
	if session and registration.conference_registrant_id:
		try:
			cancel_participant(session, registration.conference_registrant_id, registration.email)
		except Exception:
			frappe.log_error(title="Conference registrant cancel failed", message=frappe.get_traceback())

	registration.status = new_status
	registration.join_url = ""
	registration.save(ignore_permissions=True)
	if notify:
		notifications.send_registration_cancelled(registration)
	return registration


def handle_checkout_event(event_type: str, checkout: dict) -> None:
	name = checkout.get("client_reference_id") or (checkout.get("metadata") or {}).get("registration")
	if not name or not frappe.db.exists("Seminar Registration", name):
		return
	registration = frappe.get_doc("Seminar Registration", name)
	if registration.stripe_checkout_session and registration.stripe_checkout_session != checkout.get("id"):
		return

	if event_type in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
		if checkout.get("payment_status") not in ("paid", "no_payment_required"):
			return  # asynchronous method (e.g. konbini) still pending
		expected = stripe_api.to_minor_units(registration.amount, registration.currency)
		if int(checkout.get("amount_total") or 0) != expected or (
			(checkout.get("currency") or "").lower() != registration.currency.lower()
		):
			frappe.log_error(
				title="Stripe amount mismatch",
				message=f"{name}: expected {expected} {registration.currency}, got {checkout.get('amount_total')} {checkout.get('currency')}",
			)
			return
		confirm_registration(name, payment_intent=checkout.get("payment_intent"))
	elif event_type in ("checkout.session.expired", "checkout.session.async_payment_failed"):
		expire_registration(name)


def check_in(token: str) -> dict:
	registration = get_registration_by_token(token, for_update=True)
	if not registration:
		frappe.throw(_("Invalid check-in code."), frappe.DoesNotExistError)
	if registration.status != "Confirmed":
		frappe.throw(_("This registration is {0}.").format(_(registration.status)))
	already = bool(registration.checked_in)
	if not already:
		registration.checked_in = 1
		registration.checked_in_at = now_datetime()
		registration.checked_in_by = frappe.session.user
		registration.save(ignore_permissions=True)
	return {
		"already_checked_in": already,
		"attendee_name": registration.attendee_name,
		"company": registration.company,
		"ticket_type": registration.ticket_type,
		"checked_in_at": str(registration.checked_in_at),
	}


def submit_feedback(token: str, rating, comments: str | None = None, would_recommend=None) -> None:
	registration = get_registration_by_token(token)
	if not registration or registration.status != "Confirmed":
		frappe.throw(_("Invalid feedback link."), frappe.DoesNotExistError)
	seminar = frappe.db.get_value(
		"Seminar", registration.seminar, ["feedback_enabled", "starts_at"], as_dict=True
	)
	if not seminar.feedback_enabled:
		frappe.throw(_("Feedback is not collected for this seminar."))
	if now_datetime() < get_datetime(seminar.starts_at):
		frappe.throw(_("Feedback opens after the seminar starts."))
	if frappe.db.exists("Seminar Feedback", {"registration": registration.name}):
		frappe.throw(_("Feedback has already been submitted. Thank you!"))

	rating = cint(rating)
	if rating < 1 or rating > 5:
		frappe.throw(_("Rating must be between 1 and 5."))
	frappe.get_doc(
		{
			"doctype": "Seminar Feedback",
			"seminar": registration.seminar,
			"registration": registration.name,
			"rating": rating / 5,
			"would_recommend": 1 if cint(would_recommend) else 0,
			"comments": _clean_text(comments, "Comments", 5000),
		}
	).insert(ignore_permissions=True)  # authorized by the registration's secret token
