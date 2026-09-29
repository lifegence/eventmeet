"""Shared fixtures and fakes for eventmeet tests."""

from __future__ import annotations

import itertools

import frappe
from frappe.utils import add_to_date, now_datetime

from eventmeet.conferencing.providers import (
	ConferenceProvider,
	CreatedConference,
	ParticipantRecord,
	Registrant,
)

try:  # Frappe v16
	from frappe.tests import IntegrationTestCase as SeminarTestCase
except ImportError:  # Frappe v15
	from frappe.tests.utils import FrappeTestCase as SeminarTestCase

__all__ = [
	"FakeGoogleProvider",
	"FakeProvider",
	"patch_providers",
	"SeminarTestCase",
	"capture_mail",
	"make_host",
	"make_seminar",
	"make_venue",
	"reset_conference_sessions",
]


class FakeProvider(ConferenceProvider):
	"""In-memory stand-in for Zoom that records every call."""

	name = "Zoom"
	uses_host_pool = True
	supports_registration = True
	supports_webinar = True
	_ids = itertools.count(90000)

	def __init__(self):
		self.calls: list[tuple] = []
		self.participants: list[ParticipantRecord] = []
		self.summary: str | None = None

	def create(self, host, spec):
		external_id = str(next(self._ids))
		self.calls.append(("create", host, spec))
		return CreatedConference(
			external_id=external_id,
			join_url=f"https://zoom.test/j/{external_id}",
			passcode="pw",
			meeting_code=f"code-{external_id}",
		)

	def update(self, ref, spec):
		self.calls.append(("update", ref, spec))

	def delete(self, ref, notify=False):
		self.calls.append(("delete", ref, notify))

	def add_registrant(self, ref, email, first_name, last_name=""):
		self.calls.append(("add_registrant", ref.external_id, email))
		return Registrant(
			registrant_id=f"r-{email}", join_url=f"https://zoom.test/w/{ref.external_id}?tk={email}"
		)

	def cancel_registrant(self, ref, registrant_id, email):
		self.calls.append(("cancel_registrant", ref.external_id, registrant_id))

	def get_host_url(self, ref):
		return f"https://zoom.test/s/{ref.external_id}"

	def list_participants(self, ref):
		return self.participants

	def get_summary_html(self, ref):
		return self.summary

	def called(self, action: str) -> list[tuple]:
		return [call for call in self.calls if call[0] == action]


class FakeGoogleProvider(FakeProvider):
	"""Google Meet-like fake: organizer-owned sessions and native calendar invitations."""

	name = "Google Meet"
	uses_host_pool = False
	supports_registration = False
	supports_webinar = False
	native_invitations = True

	def create(self, host, spec):
		created = super().create(host, spec)
		created.join_url = f"https://meet.test/{created.meeting_code}"
		return created


def patch_providers(testcase) -> dict[str, FakeProvider]:
	"""Route get_provider() to fakes for the duration of the test."""
	from unittest.mock import patch

	fakes = {"Zoom": FakeProvider(), "Google Meet": FakeGoogleProvider()}
	patcher = patch("eventmeet.services.conference.get_provider", side_effect=lambda name: fakes[name])
	patcher.start()
	testcase.addCleanup(patcher.stop)
	return fakes


def ensure_currency(code: str = "JPY"):
	if not frappe.db.exists("Currency", code):
		frappe.get_doc(
			{"doctype": "Currency", "currency_name": code, "enabled": 1, "fraction_units": 0, "symbol": "¥"}
		).insert(ignore_permissions=True)


def make_host(label: str, meeting_capacity: int = 100, webinar_capacity: int = 0, **kwargs):
	if frappe.db.exists("Zoom Host Account", label):
		frappe.delete_doc("Zoom Host Account", label, force=True)
	return frappe.get_doc(
		{
			"doctype": "Zoom Host Account",
			"account_label": label,
			"zoom_user": f"{label.lower().replace(' ', '')}@example.com",
			"meeting_capacity": meeting_capacity,
			"webinar_capacity": webinar_capacity,
			**kwargs,
		}
	).insert(ignore_permissions=True)


def make_venue(name: str = "Test Hall"):
	if frappe.db.exists("Seminar Venue", name):
		return frappe.get_doc("Seminar Venue", name)
	return frappe.get_doc(
		{"doctype": "Seminar Venue", "venue_name": name, "capacity": 100, "address": "Tokyo"}
	).insert(ignore_permissions=True)


def make_seminar(fmt: str = "Offline", status: str = "Open", tickets=None, capacity: int = 0, **kwargs):
	ensure_currency()
	starts_at = kwargs.pop("starts_at", add_to_date(now_datetime(), days=7))
	doc = frappe.get_doc(
		{
			"doctype": "Seminar",
			"title": kwargs.pop("title", "Test Seminar"),
			"format": fmt,
			"status": status,
			"published": 1,
			"starts_at": starts_at,
			"ends_at": add_to_date(starts_at, hours=2),
			"capacity": capacity,
			"venue": None if fmt == "Online" else make_venue().name,
			"ticket_types": tickets
			or [{"ticket_name": "General", "price": 0, "currency": "JPY", "enabled": 1}],
			**kwargs,
		}
	)
	return doc.insert(ignore_permissions=True)


def capture_mail(testcase) -> list[dict]:
	"""Replace frappe.sendmail for the test: render the template (to catch template errors) and record it."""
	from unittest.mock import patch

	sent: list[dict] = []

	def fake_sendmail(**kwargs):
		kwargs["rendered"] = frappe.get_template(f"templates/emails/{kwargs['template']}.html").render(
			kwargs.get("args") or {}
		)
		sent.append(kwargs)

	patcher = patch("frappe.sendmail", side_effect=fake_sendmail)
	patcher.start()
	testcase.addCleanup(patcher.stop)
	return sent


def reset_conference_sessions():
	"""Free every host within the test transaction so allocations do not collide across tests."""
	frappe.db.sql("update `tabConference Session` set status = 'Cancelled' where status = 'Scheduled'")
