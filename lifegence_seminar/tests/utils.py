"""Shared fixtures and fakes for lifegence_seminar tests."""

from __future__ import annotations

import itertools

import frappe
from frappe.utils import add_to_date, now_datetime

from lifegence_seminar.conferencing.providers import (
	ConferenceProvider,
	CreatedConference,
	ParticipantRecord,
	Registrant,
)

try:  # Frappe v16
	from frappe.tests import IntegrationTestCase as SeminarTestCase
except ImportError:  # Frappe v15
	from frappe.tests.utils import FrappeTestCase as SeminarTestCase

__all__ = ["FakeProvider", "SeminarTestCase", "make_host", "make_seminar", "make_venue"]


class FakeProvider(ConferenceProvider):
	"""In-memory stand-in for Zoom that records every call."""

	name = "Zoom"
	_ids = itertools.count(90000)

	def __init__(self):
		self.calls: list[tuple] = []
		self.participants: list[ParticipantRecord] = []
		self.summary: str | None = None

	def create(self, host, spec):
		external_id = str(next(self._ids))
		self.calls.append(("create", host, spec))
		return CreatedConference(
			external_id=external_id, join_url=f"https://zoom.test/j/{external_id}", passcode="pw"
		)

	def update(self, kind, external_id, spec):
		self.calls.append(("update", external_id, spec))

	def delete(self, kind, external_id):
		self.calls.append(("delete", external_id))

	def add_registrant(self, kind, external_id, email, first_name, last_name=""):
		self.calls.append(("add_registrant", external_id, email))
		return Registrant(
			registrant_id=f"r-{email}", join_url=f"https://zoom.test/w/{external_id}?tk={email}"
		)

	def cancel_registrant(self, kind, external_id, registrant_id, email):
		self.calls.append(("cancel_registrant", external_id, registrant_id))

	def get_host_url(self, kind, external_id):
		return f"https://zoom.test/s/{external_id}"

	def list_participants(self, kind, external_id):
		return self.participants

	def get_summary_html(self, kind, external_id):
		return self.summary

	def called(self, action: str) -> list[tuple]:
		return [call for call in self.calls if call[0] == action]


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
