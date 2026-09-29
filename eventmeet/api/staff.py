import frappe
from frappe import _

from eventmeet.services import notifications, registration

STAFF_ROLES = ("Seminar Staff", "Seminar Manager", "System Manager")
MANAGER_ROLES = ("Seminar Manager", "System Manager")


@frappe.whitelist(methods=["POST"])
def check_in(token: str):
	frappe.only_for(STAFF_ROLES)
	return registration.check_in(token)


@frappe.whitelist(methods=["POST"])
def registration_action(registration_name: str, action: str):
	frappe.only_for(MANAGER_ROLES)
	name = registration_name
	if not frappe.db.exists("Seminar Registration", name):
		frappe.throw(_("Registration not found."), frappe.DoesNotExistError)

	if action == "confirm":
		registration.confirm_manually(name)
	elif action == "cancel":
		registration.cancel_registration(name, refund=False)
	elif action == "refund":
		registration.cancel_registration(name, refund=True)
	elif action == "resend":
		doc = frappe.get_doc("Seminar Registration", name)
		if doc.status != "Confirmed":
			frappe.throw(_("Only confirmed registrations can be resent."))
		notifications.send_registration_confirmed(doc)
	else:
		frappe.throw(_("Unknown action."))
	return frappe.db.get_value("Seminar Registration", name, "status")
