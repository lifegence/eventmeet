import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from eventmeet.services.registration import get_registration_by_token

no_cache = 1


def get_context(context):
	context.title = _("Seminar Survey")
	context.metatags = {"robots": "noindex, nofollow"}
	context.token = ""  # the page script references it even when the link is invalid
	registration = get_registration_by_token(frappe.form_dict.get("token"))
	context.registration = registration if registration and registration.status == "Confirmed" else None
	if not context.registration:
		return context
	# Only echo the stored token (never raw query input) into the page script.
	context.token = registration.access_token
	seminar = frappe.db.get_value(
		"Seminar", registration.seminar, ["title", "feedback_enabled", "starts_at"], as_dict=True
	)
	context.seminar_title = seminar.title
	context.submitted = frappe.db.exists("Seminar Feedback", {"registration": registration.name})
	context.available = seminar.feedback_enabled and now_datetime() >= get_datetime(seminar.starts_at)
	return context
