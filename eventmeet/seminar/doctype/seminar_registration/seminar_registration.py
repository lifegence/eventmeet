# Copyright (c) 2026, Lifegence and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class SeminarRegistration(Document):
	def validate(self):
		self.email = (self.email or "").strip().lower()
		if not self.access_token:
			self.access_token = frappe.generate_hash(length=40)
		if self.is_new():
			self.set_ticket_price()

	def set_ticket_price(self):
		seminar = frappe.get_doc("Seminar", self.seminar)
		ticket = next((t for t in seminar.ticket_types if t.ticket_name == self.ticket_type), None)
		if not ticket:
			frappe.throw(
				_("Ticket type {0} does not exist in seminar {1}.").format(self.ticket_type, self.seminar)
			)
		if self.amount is None or (not flt(self.amount) and flt(ticket.price)):
			self.amount = flt(ticket.price)
		self.currency = self.currency or ticket.currency or seminar.get_default_currency()
