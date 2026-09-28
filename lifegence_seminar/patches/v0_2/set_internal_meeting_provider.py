import frappe


def execute():
	"""Meetings created before the provider choice existed were all Zoom sessions."""
	frappe.db.sql(
		"""
		update `tabInternal Meeting` m
		join `tabConference Session` s on s.name = m.conference_session
		set m.conference_provider = s.provider
		where ifnull(m.conference_provider, '') = ''
		"""
	)
