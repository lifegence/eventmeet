# Copyright (c) 2026, Lifegence and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.naming import make_autoname
from frappe.utils import cint, flt, get_datetime, now_datetime
from frappe.website.website_generator import WebsiteGenerator

from eventmeet import website
from eventmeet.services import conference, todo_sync

ONLINE_ACTIVE_STATUSES = ("Open", "Closed", "Completed")
# The Registrations tab lists this many; the full list is one click away.
REGISTRATION_LIST_LIMIT = 500


class Seminar(WebsiteGenerator):
	def autoname(self):
		self.name = make_autoname("SEM-.YYYY.-.####", doc=self)

	def make_route(self):
		return f"seminars/{self.name.lower()}"

	def validate(self):
		super().validate()
		self.validate_schedule()
		self.validate_tickets()
		if self.format == "Offline" and self.conference_session and self.is_new():
			self.conference_session = None
		if self.status == "Open" and not self.published:
			frappe.msgprint(
				_("The seminar is open but not published, so it is not visible on the website."), alert=True
			)

	def validate_schedule(self):
		if get_datetime(self.ends_at) <= get_datetime(self.starts_at):
			frappe.throw(_("End time must be after start time."))
		previous = self.get_doc_before_save()
		if (
			previous
			and get_datetime(previous.registration_closes_at) == get_datetime(previous.starts_at)
			and get_datetime(self.registration_closes_at) == get_datetime(previous.registration_closes_at)
		):
			# The deadline was the default (the start time) and was not edited: follow the new start.
			self.registration_closes_at = self.starts_at
		if not self.registration_closes_at:
			self.registration_closes_at = self.starts_at
		if self.format != "Online" and not self.venue:
			frappe.throw(_("Venue is required for offline and hybrid seminars."))

	def validate_tickets(self):
		currency = self.get_default_currency()
		seen = set()
		for ticket in self.ticket_types:
			ticket.ticket_name = (ticket.ticket_name or "").strip()
			if ticket.ticket_name in seen:
				frappe.throw(_("Ticket name {0} is used more than once.").format(ticket.ticket_name))
			seen.add(ticket.ticket_name)
			ticket.currency = ticket.currency or currency
			if flt(ticket.price) < 0:
				frappe.throw(_("Ticket price cannot be negative."))
		if self.status == "Open" and not any(t.enabled for t in self.ticket_types):
			frappe.throw(_("Add at least one enabled ticket type before opening registration."))

	def get_default_currency(self) -> str:
		return frappe.db.get_single_value("Seminar Settings", "default_currency") or "JPY"

	def on_update(self):
		todo_sync.sync_todos(self)
		self.sync_conference_session()

	def on_trash(self):
		if frappe.db.exists("Seminar Registration", {"seminar": self.name}):
			frappe.throw(_("Cannot delete a seminar that has registrations. Cancel it instead."))
		if self.conference_session:
			conference.cancel_session(self.conference_session)

	# ------------------------------------------------------------------ online
	def needs_conference(self) -> bool:
		return self.format in ("Online", "Hybrid") and self.status in ONLINE_ACTIVE_STATUSES

	def sync_conference_session(self):
		session_status = (
			frappe.db.get_value("Conference Session", self.conference_session, "status")
			if self.conference_session
			else None
		)
		wants_session = self.needs_conference()

		if session_status == "Scheduled" and (self.status == "Cancelled" or self.format == "Offline"):
			conference.cancel_session(self.conference_session)
			self.db_set("join_url", "")
			return

		if not wants_session or self.status == "Completed":
			return

		if session_status == "Scheduled":
			conference.update_session(
				self.conference_session,
				topic=self.title,
				starts_at=self.starts_at,
				ends_at=self.ends_at,
				agenda=self.summary,
				purpose="seminar",
			)
			return

		if session_status is None or session_status == "Cancelled":
			session = conference.schedule_session(
				self,
				topic=self.title,
				starts_at=self.starts_at,
				ends_at=self.ends_at,
				kind=self.conference_kind or "Meeting",
				registration_required=True,
				expected_attendees=cint(self.capacity),
				purpose="seminar",
				agenda=self.summary,
			)
			self.db_set({"conference_session": session.name, "join_url": session.join_url})

	def apply_conference_attendance(self, minutes_by_email: dict):
		for registration in frappe.get_all(
			"Seminar Registration",
			filters={"seminar": self.name, "status": "Confirmed"},
			fields=["name", "email"],
		):
			minutes = minutes_by_email.get((registration.email or "").lower(), 0)
			frappe.db.set_value(
				"Seminar Registration",
				registration.name,
				{"attended_online": 1 if minutes > 0 else 0, "online_minutes": minutes},
				update_modified=False,
			)

	# ------------------------------------------------------------ registration
	def get_ticket(self, ticket_name: str):
		for ticket in self.ticket_types:
			if ticket.ticket_name == ticket_name and ticket.enabled:
				return ticket
		frappe.throw(_("Ticket type {0} is not available.").format(ticket_name))

	def get_registration_block_reason(self) -> str | None:
		if not self.published or self.status != "Open":
			return _("Registration for this seminar is not open.")
		if now_datetime() > get_datetime(self.registration_closes_at or self.starts_at):
			return _("Registration for this seminar has closed.")
		if self.format in ("Online", "Hybrid") and not self.conference_session:
			return _("The online session is not ready yet. Please try again later.")
		return None

	def validate_open_for_registration(self):
		if reason := self.get_registration_block_reason():
			frappe.throw(reason)

	@frappe.whitelist()
	def get_registration_overview(self) -> dict:
		"""Counts and the registration list for the Registrations tab.

		Uses get_list, so users only see the registrations they are allowed to read."""
		self.check_permission("read")
		registrations = frappe.get_list(
			"Seminar Registration",
			filters={"seminar": self.name},
			fields=[
				"name",
				"attendee_name",
				"email",
				"company",
				"ticket_type",
				"status",
				"checked_in",
				"attended_online",
			],
			order_by="creation asc",
			limit_page_length=0,
		)
		counts = {}
		for row in registrations:
			counts[row.status] = counts.get(row.status, 0) + 1
		return {
			"capacity": cint(self.capacity),
			"counts": counts,
			"checked_in": sum(1 for r in registrations if r.checked_in and r.status == "Confirmed"),
			"registrations": registrations[:REGISTRATION_LIST_LIMIT],
			"truncated": len(registrations) > REGISTRATION_LIST_LIMIT,
		}

	# ----------------------------------------------------------------- website
	def get_context(self, context):
		from eventmeet.services.registration import count_active

		context.no_cache = 1
		context.show_sidebar = False
		# Frappe's breadcrumb include renders the page title unescaped; the page has its own heading.
		context.no_breadcrumbs = True
		# Frappe copies the document's fields into the context, so the seminar's banner_image would
		# replace the site logo in the navbar (which reads the same name). The page uses doc.banner_image.
		context.banner_image = frappe.db.get_single_value("Website Settings", "banner_image")
		context.venue = frappe.get_doc("Seminar Venue", self.venue) if self.venue else None

		speaker_names = {row.speaker for row in self.sessions if row.speaker}
		context.speakers = {
			s.name: s
			for s in frappe.get_all(
				"Seminar Speaker",
				filters={"name": ["in", list(speaker_names) or [""]]},
				fields=["name", "full_name", "organization", "job_title", "photo", "bio"],
			)
		}

		seminar_left = None
		if cint(self.capacity):
			seminar_left = max(cint(self.capacity) - count_active(self.name), 0)
		tickets = []
		for ticket in self.ticket_types:
			if not ticket.enabled:
				continue
			left = seminar_left
			if cint(ticket.capacity):
				ticket_left = max(cint(ticket.capacity) - count_active(self.name, ticket.ticket_name), 0)
				left = ticket_left if left is None else min(left, ticket_left)
			tickets.append({"ticket": ticket, "remaining": left, "sold_out": left == 0})
		context.tickets = tickets

		context.registration_block_reason = self.get_registration_block_reason()
		context.registration_open = not context.registration_block_reason and any(
			not t["sold_out"] for t in tickets
		)
		context.csrf_token = frappe.sessions.get_csrf_token() if frappe.session.user != "Guest" else ""
		website.apply(context, "seminar_detail")
