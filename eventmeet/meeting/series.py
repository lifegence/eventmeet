# Copyright (c) 2026, Lifegence and contributors
# For license information, please see license.txt

"""Recurring internal meetings.

A series is a set of ordinary Internal Meetings that share the `series` field (the name of the
first meeting). Each occurrence has its own conferencing session, invitations, attendance and
minutes, so everything that works for a single meeting works for every occurrence.
"""

from __future__ import annotations

import calendar
import datetime

import frappe
from dateutil.relativedelta import relativedelta
from frappe import _
from frappe.utils import cint, format_datetime, get_datetime, getdate

FREQUENCIES = ("Weekdays", "Weekly", "Every 2 Weeks", "Monthly (same date)", "Monthly (same weekday)")
MAX_OCCURRENCES = 52
# Copied to every occurrence (and by "Update Following Meetings"); dates are handled separately.
SERIES_FIELDS = ("title", "location", "online", "conference_provider")
ATTENDEE_FIELDS = ("user", "optional")
GUEST_FIELDS = ("guest_name", "email", "organization", "optional")
AGENDA_FIELDS = ("topic", "presenter", "duration_minutes", "notes")
OPEN_STATUSES = ("Planned", "Invited")


def date_range_text(starts_at, ends_at) -> str:
	"""The date line of the invitation message (see meeting_invitation_message.html)."""
	return f"{format_datetime(starts_at, 'yyyy-MM-dd HH:mm')} – {format_datetime(ends_at, 'HH:mm')}"


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> int | None:
	"""Day of the n-th `weekday` of the month; n = -1 is the last one."""
	days = [
		day
		for day in range(1, calendar.monthrange(year, month)[1] + 1)
		if datetime.date(year, month, day).weekday() == weekday
	]
	if n == -1:
		return days[-1]
	return days[n - 1] if n <= len(days) else None


def _candidates(first: datetime.datetime, frequency: str):
	if frequency == "Weekdays":
		current = first
		while True:
			current += datetime.timedelta(days=1)
			if current.weekday() < 5:
				yield current
	elif frequency in ("Weekly", "Every 2 Weeks"):
		step = datetime.timedelta(weeks=1 if frequency == "Weekly" else 2)
		current = first
		while True:
			current += step
			yield current
	elif frequency == "Monthly (same date)":
		months = 0
		while True:
			months += 1
			yield first + relativedelta(months=months)  # the 31st becomes the month's last day
	elif frequency == "Monthly (same weekday)":
		# The 5th weekday of a month (e.g. the 5th Friday) means the last one.
		n = (first.day - 1) // 7 + 1
		n = -1 if n == 5 else n
		months = 0
		while True:
			months += 1
			month = first + relativedelta(day=1, months=months)
			day = _nth_weekday(month.year, month.month, first.weekday(), n)
			if day:
				yield month.replace(day=day)
	else:
		frappe.throw(_("Unknown repeat frequency: {0}").format(frequency))


def occurrence_starts(first, frequency: str, until=None, count: int | None = None) -> list:
	"""Start times of the occurrences after `first`.

	`count` is the total number of meetings including the first one; `until` is the last date."""
	first = get_datetime(first)
	count = cint(count)
	until = getdate(until) if until else None
	if not count and not until:
		frappe.throw(_("Set the number of meetings or the end date."))
	if count and count > MAX_OCCURRENCES:
		frappe.throw(_("A series can have at most {0} meetings.").format(MAX_OCCURRENCES))

	starts = []
	for start in _candidates(first, frequency):
		if until and start.date() > until:
			break
		if count and len(starts) + 1 >= count:
			break
		if len(starts) + 1 >= MAX_OCCURRENCES:
			frappe.throw(
				_("A series can have at most {0} meetings. Choose an earlier end date.").format(
					MAX_OCCURRENCES
				)
			)
		starts.append(start)
	return starts


def _rows(meeting, fieldname: str, fields: tuple) -> list[dict]:
	return [{field: row.get(field) for field in fields} for row in meeting.get(fieldname)]


def _message_for(source, starts_at, ends_at) -> str:
	message = source.invitation_message or ""
	if not message:
		return ""
	return message.replace(
		date_range_text(source.starts_at, source.ends_at), date_range_text(starts_at, ends_at)
	)


def apply_details(source, target, starts_at) -> None:
	"""Give `target` the details of `source`, at `starts_at` with the same duration."""
	starts_at = get_datetime(starts_at)
	ends_at = starts_at + (get_datetime(source.ends_at) - get_datetime(source.starts_at))
	target.update({field: source.get(field) for field in SERIES_FIELDS})
	target.update(
		{
			"starts_at": starts_at,
			"ends_at": ends_at,
			"invitation_message": _message_for(source, starts_at, ends_at),
		}
	)
	# People who stay in the meeting keep the record of their invitation.
	invited = {row.user: row.invited_at for row in target.get("attendees")}
	invited.update({(row.email or "").lower(): row.invited_at for row in target.get("external_attendees")})
	target.set(
		"attendees",
		[
			{**row, "invited_at": invited.get(row["user"])}
			for row in _rows(source, "attendees", ATTENDEE_FIELDS)
		],
	)
	target.set(
		"external_attendees",
		[
			{**row, "invited_at": invited.get((row["email"] or "").lower())}
			for row in _rows(source, "external_attendees", GUEST_FIELDS)
		],
	)
	target.set("agenda", _rows(source, "agenda", AGENDA_FIELDS))


def create_repeats(meeting, frequency: str, until=None, count=None, send_invitations=False) -> list[str]:
	if meeting.series:
		frappe.throw(_("This meeting is already part of a series."))
	if meeting.status not in OPEN_STATUSES:
		frappe.throw(_("Only planned or invited meetings can be repeated."))
	starts = occurrence_starts(meeting.starts_at, frequency, until, count)
	if not starts:
		frappe.throw(_("No meetings to create before the end date."))

	meeting.db_set("series", meeting.name)
	created = []
	for starts_at in starts:
		occurrence = frappe.new_doc("Internal Meeting")
		occurrence.organizer = meeting.organizer
		occurrence.series = meeting.name
		apply_details(meeting, occurrence, starts_at)
		occurrence.insert()
		if send_invitations:
			occurrence.send_invitations()
		created.append(occurrence.name)
	return created


def following(meeting, include_self: bool = False) -> list[str]:
	"""Open meetings of the series from this one on, in date order."""
	if not meeting.series:
		frappe.throw(_("This meeting is not part of a series."))
	names = frappe.get_all(
		"Internal Meeting",
		filters={
			"series": meeting.series,
			"status": ["in", OPEN_STATUSES],
			"starts_at": [">=" if include_self else ">", meeting.starts_at],
		},
		order_by="starts_at asc",
		pluck="name",
	)
	return [name for name in names if include_self or name != meeting.name]


def update_following(meeting) -> list[str]:
	"""Copy this meeting's details to the later open meetings; each keeps its own date."""
	starts_at = get_datetime(meeting.starts_at)
	updated = []
	for name in following(meeting):
		target = frappe.get_doc("Internal Meeting", name)
		target_start = datetime.datetime.combine(get_datetime(target.starts_at).date(), starts_at.time())
		apply_details(meeting, target, target_start)
		target.save()
		updated.append(name)
	return updated


def cancel_following(meeting) -> list[str]:
	"""Cancel this meeting and the later open meetings of the series."""
	from eventmeet.services import conference, notifications

	cancelled = []
	for name in following(meeting, include_self=True):
		target = frappe.get_doc("Internal Meeting", name)
		native = target.online and conference.provider_has_native_invitations(target.conference_session)
		target.status = "Cancelled"
		target.save()
		# Google Calendar notifies the guests itself; others get the cancellation email.
		if target.invitations_sent and not native:
			notifications.send_meeting_invitation(target, cancelled=True)
		cancelled.append(name)
	return cancelled
