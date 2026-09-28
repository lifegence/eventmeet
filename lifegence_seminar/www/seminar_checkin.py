from urllib.parse import quote

import frappe
from frappe import _

from lifegence_seminar.services.registration import get_registration_by_token

no_cache = 1
STAFF_ROLES = {"Seminar Staff", "Seminar Manager", "System Manager"}


def get_context(context):
	context.title = _("Seminar Check-in")
	context.metatags = {"robots": "noindex, nofollow"}
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=" + quote(frappe.request.full_path)
		raise frappe.Redirect
	if not STAFF_ROLES & set(frappe.get_roles()):
		raise frappe.PermissionError(_("Only seminar staff can check in attendees."))

	registration = get_registration_by_token(frappe.form_dict.get("token"))
	context.registration = registration
	# Only echo the stored token (never raw query input) into the page script.
	context.token = registration.access_token if registration else ""
	context.seminar_title = (
		frappe.db.get_value("Seminar", registration.seminar, "title") if registration else None
	)
	return context
