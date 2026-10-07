"""Outgoing emails for seminars and internal meetings."""

from __future__ import annotations

import io
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.utils import format_datetime, get_datetime, get_system_timezone, get_url


def qr_png(data: str) -> bytes:
	import pyqrcode

	buffer = io.BytesIO()
	pyqrcode.create(data, error="M").png(buffer, scale=6, quiet_zone=2)
	return buffer.getvalue()


def _seminar_context(registration) -> dict:
	from eventmeet.services.registration import checkin_url, feedback_url, status_url

	seminar = frappe.get_doc("Seminar", registration.seminar)
	venue = frappe.get_doc("Seminar Venue", seminar.venue) if seminar.venue else None
	return {
		"registration": registration,
		"seminar": seminar,
		"venue": venue,
		"starts_at": format_datetime(seminar.starts_at, "yyyy-MM-dd HH:mm"),
		"ends_at": format_datetime(seminar.ends_at, "HH:mm"),
		"status_url": status_url(registration),
		"checkin_url": checkin_url(registration),
		"feedback_url": feedback_url(registration),
		"is_online": seminar.format in ("Online", "Hybrid"),
		"is_onsite": seminar.format in ("Offline", "Hybrid"),
	}


def _send(
	recipients,
	subject: str,
	template: str,
	args: dict,
	reference,
	attachments=None,
	raise_on_error: bool = False,
) -> bool:
	"""Queue an email. Attendee notifications must never roll back payments or
	registrations (e.g. inside the Stripe webhook), so failures are logged unless
	the caller is an interactive action that should surface the error."""
	message_count = len(frappe.local.message_log or [])
	try:
		frappe.sendmail(
			recipients=recipients,
			subject=subject,
			template=template,
			args=args,
			reference_doctype=reference.doctype,
			reference_name=reference.name,
			attachments=attachments or [],
		)
		return True
	except Exception:
		if raise_on_error:
			raise
		# Do not leak mail-server setup messages to guests (e.g. on the public registration form).
		del frappe.local.message_log[message_count:]
		frappe.log_error(
			title=f"Email '{template}' failed for {reference.name}", message=frappe.get_traceback()
		)
		return False


def send_registration_confirmed(registration) -> bool:
	context = _seminar_context(registration)
	attachments = []
	if context["is_onsite"]:
		attachments.append({"fname": "checkin-qr.png", "fcontent": qr_png(context["checkin_url"])})
	return _send(
		[registration.email],
		_("Registration confirmed: {0}").format(context["seminar"].title),
		"seminar_registration_confirmed",
		context,
		registration,
		attachments,
	)


def send_seminar_reminder(registration) -> bool:
	context = _seminar_context(registration)
	return _send(
		[registration.email],
		_("Reminder: {0}").format(context["seminar"].title),
		"seminar_reminder",
		context,
		registration,
	)


def send_feedback_request(registration) -> bool:
	context = _seminar_context(registration)
	return _send(
		[registration.email],
		_("Thank you for attending {0}").format(context["seminar"].title),
		"seminar_feedback_request",
		context,
		registration,
	)


def send_registration_cancelled(registration) -> bool:
	context = _seminar_context(registration)
	return _send(
		[registration.email],
		_("Registration cancelled: {0}").format(context["seminar"].title),
		"seminar_registration_cancelled",
		context,
		registration,
	)


def _ics_escape(value: str) -> str:
	return (value or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ics_time(value) -> str:
	local = get_datetime(value).replace(tzinfo=ZoneInfo(get_system_timezone()))
	return local.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")


def _calendar_uid(meeting) -> str:
	"""The Google Calendar event's own UID for Google Meet, so calendars treat the .ics and the
	Google invitation as the same event instead of adding a duplicate."""
	if meeting.get("conference_session"):
		session = frappe.db.get_value(
			"Conference Session",
			meeting.conference_session,
			["provider", "external_id", "ical_uid"],
			as_dict=True,
		)
		if session and session.provider == "Google Meet" and session.external_id:
			# Sessions created before ical_uid was stored: Google's UID is "<event id>@google.com".
			return session.ical_uid or f"{session.external_id}@google.com"
	return f"{meeting.name}@{frappe.local.site}"


def meeting_ics(meeting, method: str = "REQUEST") -> str:
	organizer = frappe.db.get_value("User", meeting.organizer, "email") or meeting.organizer
	location = meeting.join_url or meeting.location or ""
	description = meeting.join_url or ""
	lines = [
		"BEGIN:VCALENDAR",
		"PRODID:-//EventMeet//EventMeet//EN",
		"VERSION:2.0",
		f"METHOD:{method}",
		"BEGIN:VEVENT",
		f"UID:{_calendar_uid(meeting)}",
		f"SEQUENCE:{int(get_datetime(meeting.modified).timestamp())}",
		f"DTSTAMP:{_ics_time(frappe.utils.now_datetime())}",
		f"DTSTART:{_ics_time(meeting.starts_at)}",
		f"DTEND:{_ics_time(meeting.ends_at)}",
		f"SUMMARY:{_ics_escape(meeting.title)}",
		f"LOCATION:{_ics_escape(location)}",
		f"DESCRIPTION:{_ics_escape(description)}",
		f"ORGANIZER:mailto:{organizer}",
		f"STATUS:{'CANCELLED' if method == 'CANCEL' else 'CONFIRMED'}",
	]
	participants = [(row.full_name, row.email, row.optional) for row in meeting.attendees]
	participants += [
		(row.guest_name, row.email, row.optional) for row in meeting.get("external_attendees") or []
	]
	for full_name, email, optional in participants:
		if email:
			role = "OPT-PARTICIPANT" if optional else "REQ-PARTICIPANT"
			lines.append(f"ATTENDEE;ROLE={role};CN={_ics_escape(full_name or email)}:mailto:{email}")
	lines += ["END:VEVENT", "END:VCALENDAR"]
	return "\r\n".join(lines) + "\r\n"


def send_meeting_invitation(meeting, cancelled: bool = False, only: set[str] | None = None) -> list[str]:
	"""Email the invitation (or cancellation). `only` limits recipients to these emails.

	Returns the recipients that were emailed."""
	internal = [row.email for row in meeting.attendees if row.email]
	external = [row.email for row in meeting.get("external_attendees") or [] if row.email]
	if only is not None:
		internal = [email for email in internal if email.lower() in only]
		external = [email for email in external if email.lower() in only]
	if not internal and not external:
		frappe.throw(_("Add at least one attendee with an email address."))
	method = "CANCEL" if cancelled else "REQUEST"
	subject = (_("Cancelled: {0}") if cancelled else _("Invitation: {0}")).format(meeting.title)
	args = {
		"meeting": meeting,
		"cancelled": cancelled,
		"starts_at": format_datetime(meeting.starts_at, "yyyy-MM-dd HH:mm"),
		"ends_at": format_datetime(meeting.ends_at, "HH:mm"),
	}
	attachments = [{"fname": "invite.ics", "fcontent": meeting_ics(meeting, method).encode()}]
	if internal:
		_send(
			internal,
			subject,
			"internal_meeting_invitation",
			{**args, "meeting_url": get_url(meeting.get_url())},
			meeting,
			attachments,
			raise_on_error=True,
		)
	if external:
		# External guests have no access to this system: no link back to the desk.
		_send(
			external,
			subject,
			"internal_meeting_invitation",
			{**args, "meeting_url": None},
			meeting,
			attachments,
			raise_on_error=True,
		)
	return internal + external
