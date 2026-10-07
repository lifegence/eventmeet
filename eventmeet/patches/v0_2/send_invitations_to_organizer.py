import frappe


def execute():
	"""Organizers get the invitation by default; Single doctypes do not apply new field defaults."""
	stored = frappe.db.sql(
		"select 1 from `tabSingles` where doctype = 'Conferencing Settings' "
		"and field = 'send_invitation_to_organizer'"
	)
	if not stored:
		frappe.db.set_single_value("Conferencing Settings", "send_invitation_to_organizer", 1)
