import frappe
from frappe import _

from eventmeet.services import conference


def _authorize(session_name: str, host_only: bool = False):
	session = frappe.get_doc("Conference Session", session_name)
	if not (session.reference_doctype and session.reference_name):
		frappe.only_for(("Seminar Manager", "System Manager"))
		return session

	reference = frappe.get_doc(session.reference_doctype, session.reference_name)
	reference.check_permission("write")
	if host_only and session.reference_doctype == "Internal Meeting":
		# The host link grants full host control; only the organizer or managers may open it.
		roles = set(frappe.get_roles())
		if frappe.session.user != reference.organizer and not roles & {"Seminar Manager", "System Manager"}:
			frappe.throw(_("Only the organizer can start this meeting as host."), frappe.PermissionError)
	return session


@frappe.whitelist()
def get_host_url(session: str) -> str:
	_authorize(session, host_only=True)
	return conference.get_host_url(session)


@frappe.whitelist(methods=["POST"])
def sync_attendance(session: str):
	_authorize(session)
	return conference.sync_attendance(session)


@frappe.whitelist(methods=["POST"])
def import_summary(session: str):
	_authorize(session)
	if not conference.import_summary(session):
		frappe.throw(
			_("No AI summary is available yet. Make sure AI Companion meeting summary is enabled in Zoom.")
		)
	return True
