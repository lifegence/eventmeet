"""Guest endpoints used by the public seminar pages (see docs/security/guest-endpoint-audit.md)."""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from eventmeet.services import registration


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=10 * 60)
def register(
	seminar: str,
	ticket_type: str,
	attendee_name: str,
	email: str,
	company: str | None = None,
	phone: str | None = None,
	website: str | None = None,
):
	if website:
		# Honeypot field that is hidden from humans.
		frappe.throw(_("Registration could not be completed."))
	return registration.create_registration(seminar, ticket_type, attendee_name, email, company, phone)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=10 * 60)
def submit_feedback(
	token: str, rating: int | str, comments: str | None = None, would_recommend: int | str | None = None
):
	registration.submit_feedback(token, rating, comments, would_recommend)
	return {"ok": True}
