"""Allocate licensed Zoom host accounts from a shared pool.

A licensed host can run only one meeting/webinar at a time, so the number of
licenses needed equals the peak number of concurrent sessions, not the number
of employees.
"""

from __future__ import annotations

import datetime

import frappe
from frappe import _
from frappe.utils import cint

PURPOSE_FIELDS = {"seminar": "use_for_seminars", "internal": "use_for_internal_meetings"}
CAPACITY_FIELDS = {"Meeting": "meeting_capacity", "Webinar": "webinar_capacity"}


def get_buffer() -> datetime.timedelta:
	minutes = cint(frappe.db.get_single_value("Conferencing Settings", "allocation_buffer_minutes"))
	return datetime.timedelta(minutes=max(minutes, 0))


def is_host_busy(
	host_account: str,
	starts_at: datetime.datetime,
	ends_at: datetime.datetime,
	exclude_session: str | None = None,
) -> bool:
	buffer = get_buffer()
	filters = {
		"host_account": host_account,
		"status": "Scheduled",
		"starts_at": ["<", ends_at + buffer],
		"ends_at": [">", starts_at - buffer],
	}
	if exclude_session:
		filters["name"] = ["!=", exclude_session]
	return bool(frappe.db.exists("Conference Session", filters))


def allocate_host(
	kind: str,
	starts_at: datetime.datetime,
	ends_at: datetime.datetime,
	expected_attendees: int,
	purpose: str,
) -> str:
	capacity_field = CAPACITY_FIELDS[kind]
	needed = max(cint(expected_attendees), 1)
	candidates = frappe.get_all(
		"Zoom Host Account",
		filters={"enabled": 1, PURPOSE_FIELDS[purpose]: 1, capacity_field: [">=", needed]},
		pluck="name",
		# Prefer the smallest sufficient license so large webinar licenses stay free.
		order_by=f"{capacity_field} asc, name asc",
	)
	if not candidates:
		frappe.throw(
			_("No enabled Zoom host account can host a {0} for {1} attendees.").format(_(kind), needed),
			title=_("No Zoom Host Available"),
		)

	# Serialize concurrent allocations so two sessions cannot grab the same host.
	frappe.db.sql(
		"select name from `tabZoom Host Account` where name in %(names)s for update",
		{"names": tuple(candidates)},
	)
	for host_account in candidates:
		if not is_host_busy(host_account, starts_at, ends_at):
			return host_account

	frappe.throw(
		_(
			"All Zoom host accounts are busy between {0} and {1}. Add a host account or change the time."
		).format(frappe.utils.format_datetime(starts_at), frappe.utils.format_datetime(ends_at)),
		title=_("No Zoom Host Available"),
	)
