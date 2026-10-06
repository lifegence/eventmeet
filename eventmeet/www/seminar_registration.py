import base64

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from eventmeet import website
from eventmeet.services.notifications import qr_png
from eventmeet.services.registration import checkin_url, feedback_url, get_registration_by_token

no_cache = 1


def get_context(context):
	context.title = _("Your Registration")
	context.metatags = {"robots": "noindex, nofollow"}
	registration = get_registration_by_token(frappe.form_dict.get("token"))
	context.registration = registration
	if not registration:
		return website.apply(context, "registration")

	seminar = frappe.get_doc("Seminar", registration.seminar)
	context.seminar = seminar
	context.venue = frappe.get_doc("Seminar Venue", seminar.venue) if seminar.venue else None
	context.checkout = frappe.form_dict.get("checkout")
	confirmed = registration.status == "Confirmed"
	context.show_join = confirmed and seminar.format != "Offline" and registration.join_url
	context.qr_data_uri = None
	if confirmed and seminar.format != "Online":
		context.qr_data_uri = (
			"data:image/png;base64," + base64.b64encode(qr_png(checkin_url(registration))).decode()
		)
	context.feedback_link = None
	if (
		confirmed
		and seminar.feedback_enabled
		and now_datetime() >= get_datetime(seminar.starts_at)
		and not frappe.db.exists("Seminar Feedback", {"registration": registration.name})
	):
		context.feedback_link = feedback_url(registration)
	return website.apply(context, "registration")
