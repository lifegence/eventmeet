# Copyright (c) 2026, Lifegence and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import (
	cint,
	format_datetime,
	get_datetime,
	get_fullname,
	strip_html,
	validate_email_address,
)

from eventmeet.conferencing.providers import Invitee
from eventmeet.services import conference, notifications, todo_sync

MANAGER_ROLES = {"System Manager", "Seminar Manager"}


class InternalMeeting(Document):
	def validate(self):
		if get_datetime(self.ends_at) <= get_datetime(self.starts_at):
			frappe.throw(_("End time must be after start time."))
		if self.online and not self.conference_provider:
			# Keep the tool of an existing session; only new meetings follow the current default.
			existing = (
				frappe.db.get_value("Conference Session", self.conference_session, "provider")
				if self.conference_session
				else None
			)
			self.conference_provider = existing or conference.default_internal_provider()
		self.set_attendee_details()
		self.validate_external_attendees()

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

	def validate_external_attendees(self):
		internal_emails = {(row.email or "").lower() for row in self.attendees if row.email}
		seen = set()
		for row in self.external_attendees:
			row.guest_name = strip_html(row.guest_name or "").strip()
			row.organization = strip_html(row.organization or "").strip()
			row.email = validate_email_address((row.email or "").strip(), throw=True).lower()
			if row.email in seen:
				frappe.throw(_("External attendee {0} is listed more than once.").format(row.email))
			if row.email in internal_emails:
				frappe.throw(
					_("{0} is already an internal attendee; remove it from External Attendees.").format(
						row.email
					)
				)
			seen.add(row.email)

	def on_update(self):
		todo_sync.sync_todos(self)
		self.sync_conference_session()

	def on_trash(self):
		if self.conference_session:
			conference.cancel_session(self.conference_session, notify=bool(self.invitations_sent))

	# ------------------------------------------------------------------ online
	def invitees(self) -> list[Invitee]:
		internal = [
			Invitee(email=row.email, optional=bool(row.optional))
			for row in self.attendees
			if row.email and row.user != self.organizer
		]
		external = [
			Invitee(email=row.email, optional=bool(row.optional))
			for row in self.external_attendees
			if row.email
		]
		return internal + external

	def organizer_email(self) -> str | None:
		return frappe.db.get_value("User", self.organizer, "email") if self.organizer else None

	def _session(self):
		if not self.conference_session:
			return None
		return frappe.db.get_value(
			"Conference Session", self.conference_session, ["status", "provider"], as_dict=True
		)

	def _cancel_session(self):
		conference.cancel_session(self.conference_session, notify=bool(self.invitations_sent))
		self.db_set("join_url", "")

	def sync_conference_session(self):
		session = self._session()
		scheduled = bool(session and session.status == "Scheduled")

		if scheduled and (self.status == "Cancelled" or not self.online):
			self._cancel_session()
			return
		if not self.online or self.status in ("Cancelled", "Completed"):
			return

		if scheduled and session.provider != self.conference_provider:
			# Switching tools (e.g. Zoom -> Google Meet): replace the session.
			self._cancel_session()
			scheduled = False

		if scheduled:
			conference.update_session(
				self.conference_session,
				topic=self.title,
				starts_at=self.starts_at,
				ends_at=self.ends_at,
				agenda=self.agenda_text(),
				description_html=self.invitation_message or "",
				purpose="internal",
				attendees=self.invitees(),
				notify=bool(self.invitations_sent),
			)
			return

		created = conference.schedule_session(
			self,
			topic=self.title,
			starts_at=self.starts_at,
			ends_at=self.ends_at,
			kind="Meeting",
			registration_required=False,
			expected_attendees=len(self.attendees),
			purpose="internal",
			agenda=self.agenda_text(),
			description_html=self.invitation_message or "",
			provider_name=self.conference_provider,
			organizer_email=self.organizer_email(),
			attendees=self.invitees(),
			notify=bool(self.invitations_sent),
		)
		self.db_set({"conference_session": created.name, "join_url": created.join_url})

	def agenda_text(self) -> str:
		return "\n".join(f"- {row.topic}" for row in self.agenda)

	def apply_conference_attendance(self, minutes_by_key: dict):
		rows = [("Internal Meeting Attendee", row, row.full_name) for row in self.attendees]
		rows += [("Internal Meeting Guest", row, row.guest_name) for row in self.external_attendees]
		for child_doctype, row, display_name in rows:
			minutes = minutes_by_key.get(conference.attendance_key(row.email, None), 0) or minutes_by_key.get(
				conference.attendance_key(None, display_name), 0
			)
			frappe.db.set_value(
				child_doctype,
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
	def build_invitation_message(self) -> str:
		"""Invitation text with the meeting overview and agenda (works on unsaved form values)."""
		agenda = [
			frappe._dict(
				topic=row.topic,
				duration_minutes=row.duration_minutes,
				presenter_name=get_fullname(row.presenter) if row.presenter else "",
			)
			for row in self.agenda
			if row.topic
		]
		return frappe.render_template(
			"eventmeet/templates/includes/meeting_invitation_message.html",
			{
				"meeting": self,
				"starts_at": format_datetime(self.starts_at, "yyyy-MM-dd HH:mm") if self.starts_at else "",
				"ends_at": format_datetime(self.ends_at, "HH:mm") if self.ends_at else "",
				"organizer_name": get_fullname(self.organizer) if self.organizer else "",
				"agenda": agenda,
				"total_minutes": sum(cint(row.duration_minutes) for row in agenda),
			},
		).strip()

	@frappe.whitelist()
	def send_invitations(self):
		self.check_permission("write")
		native = self.online and conference.provider_has_native_invitations(self.conference_session)
		if native:
			if self.status == "Cancelled":
				frappe.throw(
					_("Google Calendar notifies attendees automatically when the meeting is cancelled.")
				)
			# Google Calendar sends (or re-sends) the invitations to every attendee.
			conference.update_session(
				self.conference_session,
				topic=self.title,
				starts_at=self.starts_at,
				ends_at=self.ends_at,
				agenda=self.agenda_text(),
				description_html=self.invitation_message or "",
				purpose="internal",
				attendees=self.invitees(),
				notify=True,
			)
		else:
			notifications.send_meeting_invitation(self, cancelled=self.status == "Cancelled")
		values = {"invitations_sent": 1}
		if self.status == "Planned":
			values["status"] = "Invited"
		self.db_set(values)
		return "google" if native else "email"


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
