# Copyright (c) 2026, Lifegence and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, get_fullname

from lifegence_seminar.services import conference, notifications, todo_sync

MANAGER_ROLES = {"System Manager", "Seminar Manager"}


class InternalMeeting(Document):
	def validate(self):
		if get_datetime(self.ends_at) <= get_datetime(self.starts_at):
			frappe.throw(_("End time must be after start time."))
		self.set_attendee_details()

	def set_attendee_details(self):
		seen = set()
		if self.organizer and self.organizer not in {row.user for row in self.attendees}:
			self.append("attendees", {"user": self.organizer})
		for row in self.attendees:
			if row.user in seen:
				frappe.throw(_("Attendee {0} is listed more than once.").format(row.user))
			seen.add(row.user)
			row.full_name = get_fullname(row.user)
			row.email = frappe.db.get_value("User", row.user, "email")

	def on_update(self):
		todo_sync.sync_todos(self)
		self.sync_conference_session()

	def on_trash(self):
		if self.conference_session:
			conference.cancel_session(self.conference_session)

	def sync_conference_session(self):
		session_status = (
			frappe.db.get_value("Conference Session", self.conference_session, "status")
			if self.conference_session
			else None
		)
		if session_status == "Scheduled" and (self.status == "Cancelled" or not self.online):
			conference.cancel_session(self.conference_session)
			self.db_set("join_url", "")
			return
		if not self.online or self.status in ("Cancelled", "Completed"):
			return
		if session_status == "Scheduled":
			conference.reschedule_session(
				self.conference_session,
				topic=self.title,
				starts_at=self.starts_at,
				ends_at=self.ends_at,
				agenda=self.agenda_text(),
				purpose="internal",
			)
		elif session_status in (None, "Cancelled"):
			session = conference.schedule_session(
				self,
				topic=self.title,
				starts_at=self.starts_at,
				ends_at=self.ends_at,
				kind="Meeting",
				registration_required=False,
				expected_attendees=len(self.attendees),
				purpose="internal",
				agenda=self.agenda_text(),
			)
			self.db_set({"conference_session": session.name, "join_url": session.join_url})

	def agenda_text(self) -> str:
		return "\n".join(f"- {row.topic}" for row in self.agenda)

	def apply_conference_attendance(self, minutes_by_email: dict):
		for row in self.attendees:
			minutes = minutes_by_email.get((row.email or "").lower(), 0)
			frappe.db.set_value(
				"Internal Meeting Attendee",
				row.name,
				{"attended": 1 if minutes > 0 else 0, "attended_minutes": minutes},
				update_modified=False,
			)

	def apply_conference_summary(self, summary_html: str):
		values = {"ai_summary": summary_html}
		if not (self.minutes or "").strip():
			values["minutes"] = summary_html
		self.db_set(values, update_modified=False)

	@frappe.whitelist()
	def send_invitations(self):
		self.check_permission("write")
		notifications.send_meeting_invitation(self, cancelled=self.status == "Cancelled")
		if self.status == "Planned":
			self.db_set("status", "Invited")
		return True


def _is_manager(user: str) -> bool:
	return bool(MANAGER_ROLES & set(frappe.get_roles(user)))


def get_permission_query_conditions(user: str | None = None) -> str:
	user = user or frappe.session.user
	if user == "Administrator" or _is_manager(user):
		return ""
	escaped = frappe.db.escape(user)
	return (
		f"(`tabInternal Meeting`.organizer = {escaped} or `tabInternal Meeting`.owner = {escaped} "
		f"or exists (select 1 from `tabInternal Meeting Attendee` a where a.parent = `tabInternal Meeting`.name "
		f"and a.parenttype = 'Internal Meeting' and a.user = {escaped}))"
	)


def has_permission(doc, ptype: str | None = None, user: str | None = None) -> bool:
	user = user or frappe.session.user
	if user == "Administrator" or _is_manager(user):
		return True
	if doc.is_new() and ptype == "create":
		return True
	if user in (doc.organizer, doc.owner):
		return True
	# Attendees can read the meeting and edit minutes/action items collaboratively.
	return ptype in ("read", "print", "email", "write") and user in {row.user for row in doc.attendees}
