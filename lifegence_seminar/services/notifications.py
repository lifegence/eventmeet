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
	from lifegence_seminar.services.registration import checkin_url, feedback_url, status_url

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


def _send(recipients, subject: str, template: str, args: dict, reference, attachments=None, now=False):
	frappe.sendmail(
		recipients=recipients,
		subject=subject,
		template=template,
		args=args,
		reference_doctype=reference.doctype,
		reference_name=reference.name,
		attachments=attachments or [],
		now=now,
	)


def send_registration_confirmed(registration) -> None:
	context = _seminar_context(registration)
	attachments = []
	if context["is_onsite"]:
		attachments.append({"fname": "checkin-qr.png", "fcontent": qr_png(context["checkin_url"])})
	_send(
		[registration.email],
		_("Registration confirmed: {0}").format(context["seminar"].title),
		"seminar_registration_confirmed",
		context,
		registration,
		attachments,
	)


def send_seminar_reminder(registration) -> None:
	context = _seminar_context(registration)
	_send(
		[registration.email],
		_("Reminder: {0}").format(context["seminar"].title),
		"seminar_reminder",
		context,
		registration,
	)


def send_feedback_request(registration) -> None:
	context = _seminar_context(registration)
	_send(
		[registration.email],
		_("Thank you for attending {0}").format(context["seminar"].title),
		"seminar_feedback_request",
		context,
		registration,
	)


def send_registration_cancelled(registration) -> None:
	context = _seminar_context(registration)
	_send(
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


def meeting_ics(meeting, method: str = "REQUEST") -> str:
	organizer = frappe.db.get_value("User", meeting.organizer, "email") or meeting.organizer
	location = meeting.join_url or meeting.location or ""
	description = meeting.join_url or ""
	lines = [
		"BEGIN:VCALENDAR",
		"PRODID:-//Lifegence//Lifegence Seminar//EN",
		"VERSION:2.0",
		f"METHOD:{method}",
		"BEGIN:VEVENT",
		f"UID:{meeting.name}@{frappe.local.site}",
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
	for attendee in meeting.attendees:
		if attendee.email:
			role = "OPT-PARTICIPANT" if attendee.optional else "REQ-PARTICIPANT"
			lines.append(
				f"ATTENDEE;ROLE={role};CN={_ics_escape(attendee.full_name or attendee.email)}:mailto:{attendee.email}"
			)
	lines += ["END:VEVENT", "END:VCALENDAR"]
	return "\r\n".join(lines) + "\r\n"


def send_meeting_invitation(meeting, cancelled: bool = False) -> None:
	recipients = [row.email for row in meeting.attendees if row.email]
	if not recipients:
		frappe.throw(_("Add at least one attendee with an email address."))
	method = "CANCEL" if cancelled else "REQUEST"
	subject = (_("Cancelled: {0}") if cancelled else _("Invitation: {0}")).format(meeting.title)
	_send(
		recipients,
		subject,
		"internal_meeting_invitation",
		{
			"meeting": meeting,
			"cancelled": cancelled,
			"starts_at": format_datetime(meeting.starts_at, "yyyy-MM-dd HH:mm"),
			"ends_at": format_datetime(meeting.ends_at, "HH:mm"),
			"meeting_url": get_url(meeting.get_url()),
		},
		meeting,
		[{"fname": "invite.ics", "fcontent": meeting_ics(meeting, method).encode()}],
	)
