"""Provider-agnostic orchestration of online sessions (Conference Session)."""

from __future__ import annotations

import datetime
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import (
	add_to_date,
	cint,
	get_datetime,
	get_system_timezone,
	now_datetime,
	time_diff_in_seconds,
)

from lifegence_seminar.conferencing.providers import ConferenceProviderError, ConferenceSpec, get_provider
from lifegence_seminar.services.host_pool import allocate_host, is_host_busy

DEFAULT_PROVIDER = "Zoom"
MAX_ATTENDANCE_SYNC_ATTEMPTS = 12
SUMMARY_WINDOW_HOURS = 48


def _duration_minutes(starts_at: datetime.datetime, ends_at: datetime.datetime) -> int:
	minutes = int(time_diff_in_seconds(ends_at, starts_at) // 60)
	if minutes <= 0:
		frappe.throw(_("End time must be after start time."))
	return minutes


def _spec(topic, kind, starts_at, ends_at, registration_required, agenda, purpose) -> ConferenceSpec:
	settings = frappe.get_single("Conferencing Settings")
	return ConferenceSpec(
		topic=topic,
		kind=kind,
		starts_at=starts_at,
		duration_minutes=_duration_minutes(starts_at, ends_at),
		timezone=get_system_timezone(),
		registration_required=registration_required,
		agenda=agenda or "",
		waiting_room=purpose == "internal" and bool(settings.zoom_waiting_room),
		auto_recording=settings.zoom_auto_recording or "none",
	)


def _raise(action: str, error: Exception):
	frappe.log_error(title=f"Conference {action} failed", message=frappe.get_traceback())
	frappe.throw(
		_("Could not {0} the online session: {1}").format(_(action), error), title=_("Conferencing Error")
	)


def schedule_session(
	reference_doc,
	*,
	topic: str,
	starts_at,
	ends_at,
	kind: str,
	registration_required: bool,
	expected_attendees: int,
	purpose: str,
	agenda: str = "",
):
	starts_at, ends_at = get_datetime(starts_at), get_datetime(ends_at)
	spec = _spec(topic, kind, starts_at, ends_at, registration_required, agenda, purpose)
	host_account = allocate_host(kind, starts_at, ends_at, expected_attendees, purpose)
	host_user = frappe.db.get_value("Zoom Host Account", host_account, "zoom_user")
	provider = get_provider(DEFAULT_PROVIDER)

	try:
		created = provider.create(host_user, spec)
	except ConferenceProviderError as e:
		_raise("create", e)

	try:
		session = frappe.get_doc(
			{
				"doctype": "Conference Session",
				"topic": topic,
				"provider": provider.name,
				"kind": kind,
				"status": "Scheduled",
				"reference_doctype": reference_doc.doctype,
				"reference_name": reference_doc.name,
				"host_account": host_account,
				"starts_at": starts_at,
				"ends_at": ends_at,
				"duration_minutes": spec.duration_minutes,
				"timezone": spec.timezone,
				"external_id": created.external_id,
				"join_url": created.join_url,
				"passcode": created.passcode,
				"registration_required": 1 if registration_required else 0,
			}
		)
		session.insert(ignore_permissions=True)
	except Exception:
		# Do not leave an orphan meeting on the provider side.
		try:
			provider.delete(kind, created.external_id)
		except ConferenceProviderError:
			frappe.log_error(title="Orphan conference cleanup failed", message=frappe.get_traceback())
		raise
	return session


def reschedule_session(session_name: str, *, topic: str, starts_at, ends_at, agenda: str = "", purpose: str):
	session = frappe.get_doc("Conference Session", session_name)
	starts_at, ends_at = get_datetime(starts_at), get_datetime(ends_at)
	if (
		session.topic == topic
		and get_datetime(session.starts_at) == starts_at
		and get_datetime(session.ends_at) == ends_at
	):
		return session

	if is_host_busy(session.host_account, starts_at, ends_at, exclude_session=session.name):
		frappe.throw(
			_("Host account {0} is busy at the new time. Choose another time.").format(session.host_account),
			title=_("No Zoom Host Available"),
		)

	spec = _spec(
		topic, session.kind, starts_at, ends_at, bool(session.registration_required), agenda, purpose
	)
	try:
		get_provider(session.provider).update(session.kind, session.external_id, spec)
	except ConferenceProviderError as e:
		_raise("update", e)

	session.update(
		{
			"topic": topic,
			"starts_at": starts_at,
			"ends_at": ends_at,
			"duration_minutes": spec.duration_minutes,
		}
	)
	session.save(ignore_permissions=True)
	return session


def cancel_session(session_name: str):
	session = frappe.get_doc("Conference Session", session_name)
	if session.status == "Cancelled":
		return session
	try:
		get_provider(session.provider).delete(session.kind, session.external_id)
	except ConferenceProviderError as e:
		_raise("cancel", e)
	session.status = "Cancelled"
	session.save(ignore_permissions=True)
	return session


def register_participant(session_name: str, email: str, full_name: str):
	"""Return (registrant_id, personal join URL)."""
	session = frappe.get_doc("Conference Session", session_name)
	if not session.registration_required:
		return "", session.join_url
	registrant = get_provider(session.provider).add_registrant(
		session.kind, session.external_id, email, full_name
	)
	return registrant.registrant_id, registrant.join_url or session.join_url


def cancel_participant(session_name: str, registrant_id: str, email: str) -> None:
	session = frappe.get_doc("Conference Session", session_name)
	if session.status == "Cancelled" or not registrant_id:
		return
	get_provider(session.provider).cancel_registrant(session.kind, session.external_id, registrant_id, email)


def get_host_url(session_name: str) -> str:
	session = frappe.get_doc("Conference Session", session_name)
	try:
		return get_provider(session.provider).get_host_url(session.kind, session.external_id)
	except ConferenceProviderError as e:
		_raise("open", e)


def _reference_doc(session):
	if session.reference_doctype and session.reference_name:
		if frappe.db.exists(session.reference_doctype, session.reference_name):
			return frappe.get_doc(session.reference_doctype, session.reference_name)
	return None


def sync_attendance(session_name: str) -> dict[str, float]:
	"""Fetch participant report and push per-email minutes to the reference document."""
	session = frappe.get_doc("Conference Session", session_name)
	records = get_provider(session.provider).list_participants(session.kind, session.external_id)

	minutes_by_email: dict[str, float] = defaultdict(float)
	session.set("participants", [])
	for record in records:
		session.append(
			"participants",
			{
				"participant_name": record.name,
				"email": record.email,
				"join_time": record.join_time,
				"leave_time": record.leave_time,
				"duration_minutes": record.duration_minutes,
			},
		)
		if record.email:
			minutes_by_email[record.email] += record.duration_minutes

	session.attendance_synced = 1
	session.attendance_sync_attempts = cint(session.attendance_sync_attempts) + 1
	if session.status == "Scheduled":
		session.status = "Ended"
	session.save(ignore_permissions=True)

	reference = _reference_doc(session)
	if reference and hasattr(reference, "apply_conference_attendance"):
		reference.apply_conference_attendance(dict(minutes_by_email))
	return dict(minutes_by_email)


def import_summary(session_name: str) -> bool:
	session = frappe.get_doc("Conference Session", session_name)
	summary_html = get_provider(session.provider).get_summary_html(session.kind, session.external_id)
	if not summary_html:
		return False
	reference = _reference_doc(session)
	if reference and hasattr(reference, "apply_conference_summary"):
		reference.apply_conference_summary(summary_html)
	session.db_set("summary_imported", 1)
	return True


def mark_ended(external_id: str) -> None:
	for name in frappe.get_all(
		"Conference Session", filters={"external_id": external_id, "status": "Scheduled"}, pluck="name"
	):
		frappe.db.set_value("Conference Session", name, "status", "Ended")


def process_ended_sessions() -> None:
	delay = cint(frappe.db.get_single_value("Conferencing Settings", "attendance_sync_delay_minutes")) or 15
	now = now_datetime()
	sessions = frappe.get_all(
		"Conference Session",
		filters={
			"status": ["!=", "Cancelled"],
			"ends_at": [
				"between",
				[add_to_date(now, hours=-SUMMARY_WINDOW_HOURS), add_to_date(now, minutes=-delay)],
			],
		},
		fields=[
			"name",
			"kind",
			"attendance_synced",
			"attendance_sync_attempts",
			"summary_imported",
			"reference_doctype",
		],
	)
	for session in sessions:
		if (
			not session.attendance_synced
			and cint(session.attendance_sync_attempts) < MAX_ATTENDANCE_SYNC_ATTEMPTS
		):
			if not _run_safely(sync_attendance, session.name):
				# Reports are often not ready right after the session; count the attempt and retry later.
				frappe.db.set_value(
					"Conference Session",
					session.name,
					"attendance_sync_attempts",
					cint(session.attendance_sync_attempts) + 1,
					update_modified=False,
				)
				frappe.db.commit()
		if (
			session.kind == "Meeting"
			and session.reference_doctype == "Internal Meeting"
			and not session.summary_imported
		):
			_run_safely(import_summary, session.name)


def _run_safely(fn, session_name: str) -> bool:
	"""Run one session job in its own transaction so a failure does not affect the others."""
	try:
		fn(session_name)
		frappe.db.commit()
		return True
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title=f"{fn.__name__} failed for {session_name}", message=frappe.get_traceback())
		return False
