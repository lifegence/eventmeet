# Copyright (c) 2026, Lifegence and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model import no_value_fields, table_fields
from frappe.model.document import Document
from frappe.utils import (
	cint,
	format_datetime,
	get_datetime,
	get_fullname,
	now_datetime,
	strip_html,
	validate_email_address,
)

from eventmeet.conferencing.providers import Invitee
from eventmeet.services import conference, notifications, todo_sync

MANAGER_ROLES = {"System Manager", "Seminar Manager"}
# What attendees who do not organize the meeting may change: the shared minutes and action items.
ATTENDEE_EDITABLE_FIELDS = frozenset({"minutes", "actions"})


class InternalMeeting(Document):
	def validate(self):
		self.validate_organizer()
		self.keep_organizer_fields()
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

	def validate_organizer(self):
		if self.flags.ignore_permissions or is_admin_or_manager(frappe.session.user):
			return
		previous = self.get_doc_before_save()
		if previous is None and self.organizer != frappe.session.user:
			frappe.throw(_("You can only create meetings that you organize."), frappe.PermissionError)
		if previous is not None and previous.organizer != self.organizer:
			frappe.throw(_("Only a Seminar Manager can change the organizer."), frappe.PermissionError)

	def keep_organizer_fields(self):
		"""Attendees edit only the minutes and action items; anything else they send is discarded.

		Discarding (rather than rejecting) keeps a stale form from failing when the system has
		updated attendance or invitation fields since it was loaded.
		"""
		previous = self.get_doc_before_save()
		if previous is None or self.flags.ignore_permissions or self.can_manage():
			return
		for df in self.meta.fields:
			if df.fieldname in ATTENDEE_EDITABLE_FIELDS:
				continue
			if df.fieldtype in table_fields:
				self.set(df.fieldname, [row.as_dict() for row in previous.get(df.fieldname)])
			elif df.fieldtype not in no_value_fields:
				self.set(df.fieldname, previous.get(df.fieldname))

	def can_manage(self, user: str | None = None) -> bool:
		"""Organizer-level rights: edit everything and send invitations."""
		user = user or frappe.session.user
		return user in (self.organizer, self.owner) or is_admin_or_manager(user)

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
			if not self.conference_details_changed():
				# e.g. only minutes / action items were edited: nothing to push, and no
				# notification to attendees (Google Calendar would email everyone).
				return
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

	def conference_signature(self) -> tuple:
		"""Everything that is sent to the conferencing provider / calendar invitation."""
		return (
			self.title,
			str(get_datetime(self.starts_at)),
			str(get_datetime(self.ends_at)),
			self.invitation_message or "",
			self.agenda_text(),
			tuple(sorted((i.email, bool(i.optional)) for i in self.invitees())),
		)

	def conference_details_changed(self) -> bool:
		previous = self.get_doc_before_save()
		return previous is None or previous.conference_signature() != self.conference_signature()

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
		# The template path is a constant; user input only reaches the template as context values.
		return frappe.render_template(  # nosemgrep: frappe-ssti
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
	def send_invitations(self, recipients: list[str] | str | None = None):
		"""Send the invitation to everyone, or only to `recipients` (emails selected in the attendee tables)."""
		self.check_permission("write")
		if not self.can_manage():
			frappe.throw(_("Only the organizer can send invitations."), frappe.PermissionError)
		selected = self._selected_recipients(recipients)
		native = self.online and conference.provider_has_native_invitations(self.conference_session)
		cancelled = self.status == "Cancelled"
		if native and cancelled:
			frappe.throw(_("Google Calendar notifies attendees automatically when the meeting is cancelled."))

		if selected is not None:
			# Google Calendar can only notify everyone, so selected people get an email from this
			# system instead (its .ics carries the Google event's UID, so no duplicate event).
			sent = notifications.send_meeting_invitation(self, cancelled=cancelled, only=selected)
			self._mark_invited(sent)
			self.add_comment("Info", _("Invitation sent to: {0}").format(", ".join(sent)))
			return "selected"

		if native:
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
			self._mark_invited([i.email for i in self.invitees()])
			organizer_email = self.organizer_email()
			if organizer_email and self.send_to_organizer():
				# Google does not email the organizer about their own event, so send them a copy.
				sent = notifications.send_meeting_invitation(self, only={organizer_email.lower()})
				self._mark_invited(sent)
		else:
			only = None
			if not self.send_to_organizer():
				only = self.participant_emails() - {(self.organizer_email() or "").lower()}
			sent = notifications.send_meeting_invitation(self, cancelled=cancelled, only=only)
			self._mark_invited(sent)
		values = {"invitations_sent": 1}
		if self.status == "Planned":
			values["status"] = "Invited"
		self.db_set(values)
		return "google" if native else "email"

	@staticmethod
	def send_to_organizer() -> bool:
		"""Whether a full send also emails the organizer (people picked in the tables always get it)."""
		return bool(cint(frappe.db.get_single_value("Conferencing Settings", "send_invitation_to_organizer")))

	def participant_emails(self) -> set[str]:
		rows = list(self.attendees) + list(self.external_attendees)
		return {row.email.lower() for row in rows if row.email}

	def _selected_recipients(self, recipients) -> set[str] | None:
		"""None means everyone."""
		if isinstance(recipients, str):
			recipients = frappe.parse_json(recipients)
		if not recipients:
			return None
		selected = {str(email).strip().lower() for email in recipients if email}
		everyone = self.participant_emails()
		unknown = selected - everyone
		if unknown:
			frappe.throw(_("Not an attendee of this meeting: {0}").format(", ".join(sorted(unknown))))
		return None if selected == everyone else selected

	def _mark_invited(self, emails) -> None:
		emails = {email.lower() for email in emails}
		now = now_datetime()
		for child_doctype, rows in (
			("Internal Meeting Attendee", self.attendees),
			("Internal Meeting Guest", self.external_attendees),
		):
			for row in rows:
				if row.email and row.email.lower() in emails:
					frappe.db.set_value(child_doctype, row.name, "invited_at", now, update_modified=False)


def _is_manager(user: str) -> bool:
	return bool(MANAGER_ROLES & set(frappe.get_roles(user)))


def is_admin_or_manager(user: str) -> bool:
	return user == "Administrator" or _is_manager(user)


def get_permission_query_conditions(user: str | None = None) -> str:
	user = user or frappe.session.user
	if is_admin_or_manager(user):
		return ""
	escaped = frappe.db.escape(user)
	return (
		f"(`tabInternal Meeting`.organizer = {escaped} or `tabInternal Meeting`.owner = {escaped} "
		f"or exists (select 1 from `tabInternal Meeting Attendee` a where a.parent = `tabInternal Meeting`.name "
		f"and a.parenttype = 'Internal Meeting' and a.user = {escaped}))"
	)


def has_permission(doc, ptype: str | None = None, user: str | None = None) -> bool:
	user = user or frappe.session.user
	if is_admin_or_manager(user):
		return True
	if doc.is_new() and ptype == "create":
		return True
	if user in (doc.organizer, doc.owner):
		return True
	# Attendees can read the meeting and edit minutes/action items collaboratively
	# (keep_organizer_fields discards their changes to anything else).
	return ptype in ("read", "print", "email", "write") and user in {row.user for row in doc.attendees}
