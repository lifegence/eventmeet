"""Outgoing emails for seminars and internal meetings."""

from __future__ import annotations

import io
import re
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.utils import cint, format_datetime, get_datetime, get_system_timezone, get_url


def qr_png(data: str) -> bytes:
	import pyqrcode

	buffer = io.BytesIO()
	pyqrcode.create(data, error="M").png(buffer, scale=6, quiet_zone=2)
	return buffer.getvalue()


def contact_email(seminar) -> str:
	return (
		seminar.get("contact_email") or frappe.db.get_single_value("Seminar Settings", "contact_email") or ""
	)


WEEKDAYS_JA = "月火水木金土日"
DEFAULT_ACCENT = "#1a1a1a"


def format_moment(value, with_date: bool = True) -> str:
	"""A date and time for attendees: "2026年11月30日（月）12:00" in Japanese, "Mon, Nov 30, 2026 12:00" otherwise."""
	if not value:
		return ""
	value = get_datetime(value)
	time = value.strftime("%H:%M")
	if not with_date:
		return time
	if (frappe.local.lang or "").startswith("ja"):
		return f"{value.year}年{value.month}月{value.day}日（{WEEKDAYS_JA[value.weekday()]}）{time}"
	return f"{value.strftime('%a, %b')} {value.day}, {value.year} {time}"


def format_period(starts_at, ends_at) -> str:
	starts, ends = get_datetime(starts_at), get_datetime(ends_at)
	end = format_moment(ends, with_date=starts.date() != ends.date())
	separator = "〜" if (frappe.local.lang or "").startswith("ja") else " – "
	return f"{format_moment(starts)}{separator}{end}"


def email_brand() -> dict:
	"""Logo, accent colour and footer of the attendee emails (Seminar Settings > Email Design)."""
	settings = frappe.get_cached_doc("Seminar Settings")
	logo = settings.get("email_logo") or frappe.db.get_single_value("Website Settings", "app_logo") or ""
	accent = (settings.get("email_accent_color") or "").strip()
	if not re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?", accent):
		accent = DEFAULT_ACCENT
	return {
		"name": settings.get("email_brand_name")
		or frappe.db.get_single_value("Website Settings", "app_name")
		or frappe.db.get_single_value("System Settings", "app_name")
		or "",
		"logo_url": get_url(logo) if logo else "",
		"logo_width": cint(settings.get("email_logo_width")) or 120,
		"accent": accent,
		"footer": settings.get("email_footer") or "",
	}


def _seminar_context(registration, include_join: bool | None = None) -> dict:
	"""`include_join`: whether the email gives the join link; by default when it is due."""
	from eventmeet.services.registration import (
		checkin_url,
		feedback_url,
		join_info_ready,
		join_url_for,
		status_url,
	)

	seminar = frappe.get_doc("Seminar", registration.seminar)
	venue = frappe.get_doc("Seminar Venue", seminar.venue) if seminar.venue else None
	if include_join is None:
		include_join = join_info_ready(registration, seminar)
	return {
		"brand": email_brand(),
		"join_url": join_url_for(registration, seminar) if include_join else "",
		"joining_instructions": seminar.get("joining_instructions") or "",
		"join_info_send_at": format_moment(seminar.get("join_info_send_at")),
		"contact_email": contact_email(seminar),
		"registration": registration,
		"seminar": seminar,
		"venue": venue,
		"when": format_period(seminar.starts_at, seminar.ends_at),
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
	immediate: bool = False,
) -> bool:
	"""Queue an email. Attendee notifications must never roll back payments or
	registrations (e.g. inside the Stripe webhook), so failures are logged unless
	the caller is an interactive action that should surface the error.

	`immediate`: send it from a background job right after the commit instead of waiting for the
	scheduler's queue flush (which runs every few minutes)."""
	message_count = len(frappe.local.message_log or [])
	try:
		queue = frappe.sendmail(
			recipients=recipients,
			subject=subject,
			template=template,
			args=args,
			reference_doctype=reference.doctype,
			reference_name=reference.name,
			attachments=attachments or [],
		)
		if immediate:
			_send_after_commit(queue)
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


def _send_after_commit(queue) -> None:
	name = getattr(queue, "name", None)
	if not name:
		return
	try:
		frappe.enqueue(
			"frappe.email.doctype.email_queue.email_queue.send_now",
			name=name,
			queue="short",
			enqueue_after_commit=True,
		)
	except Exception:
		# The scheduler's queue flush still sends it.
		frappe.log_error(title=f"Could not send email {name} immediately", message=frappe.get_traceback())


SEMINAR_EMAILS = {
	"confirmation": ("Registration confirmed: {0}", "seminar_registration_confirmed"),
	"join_info": ("Join information: {0}", "seminar_join_info"),
	"reminder": ("Reminder: {0}", "seminar_reminder"),
	"cancellation": ("Registration cancelled: {0}", "seminar_registration_cancelled"),
	"feedback": ("Thank you for attending {0}", "seminar_feedback_request"),
}


def seminar_email_subject(kind: str, seminar) -> str:
	return _(SEMINAR_EMAILS[kind][0]).format(seminar.title)


def render_preview(seminar_name: str, kind: str) -> dict:
	"""The email `kind` of a seminar for a sample registrant, as it would be sent now (nothing is saved)."""
	if kind not in SEMINAR_EMAILS:
		frappe.throw(_("Unknown email: {0}").format(kind))
	seminar = frappe.get_doc("Seminar", seminar_name)
	ticket = next((t for t in seminar.ticket_types if t.enabled), None)
	registration = frappe.get_doc(
		{
			"doctype": "Seminar Registration",
			"name": "PREVIEW",
			"seminar": seminar.name,
			"ticket_type": ticket.ticket_name if ticket else "",
			"attendee_name": _("Taro Yamada"),
			"email": "taro@example.com",
			"status": "Cancelled" if kind == "cancellation" else "Confirmed",
			"access_token": "preview",
			"join_url": "https://zoom.us/j/0000000000?tk=preview" if seminar.format != "Offline" else "",
		}
	)
	include_join = kind in ("join_info", "reminder") or None
	context = _seminar_context(registration, include_join)
	if kind in ("join_info", "reminder") and not context["join_url"]:
		context["join_url"] = seminar.get("own_join_url") or registration.join_url
	html = frappe.get_template(f"templates/emails/{SEMINAR_EMAILS[kind][1]}.html").render(context)
	return {"subject": seminar_email_subject(kind, seminar), "html": html}


def send_registration_confirmed(registration, include_join: bool | None = None) -> bool:
	context = _seminar_context(registration, include_join)
	attachments = []
	if context["is_onsite"]:
		attachments.append({"fname": "checkin-qr.png", "fcontent": qr_png(context["checkin_url"])})
	return _send(
		[registration.email],
		seminar_email_subject("confirmation", context["seminar"]),
		"seminar_registration_confirmed",
		context,
		registration,
		attachments,
		immediate=True,
	)


def send_join_info(registration) -> bool:
	context = _seminar_context(registration, include_join=True)
	return _send(
		[registration.email],
		seminar_email_subject("join_info", context["seminar"]),
		"seminar_join_info",
		context,
		registration,
		immediate=True,
	)


def send_seminar_reminder(registration) -> bool:
	context = _seminar_context(registration)
	return _send(
		[registration.email],
		seminar_email_subject("reminder", context["seminar"]),
		"seminar_reminder",
		context,
		registration,
		immediate=True,
	)


def send_feedback_request(registration) -> bool:
	context = _seminar_context(registration)
	return _send(
		[registration.email],
		seminar_email_subject("feedback", context["seminar"]),
		"seminar_feedback_request",
		context,
		registration,
	)


def send_registration_cancelled(registration) -> bool:
	context = _seminar_context(registration)
	return _send(
		[registration.email],
		seminar_email_subject("cancellation", context["seminar"]),
		"seminar_registration_cancelled",
		context,
		registration,
		immediate=True,
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
