# Copyright (c) 2026, Lifegence and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document


class ConferencingSettings(Document):
	def validate(self):
		self.validate_google_key()
		if self.internal_meeting_provider == "Google Meet" and not self.google_meet_enabled:
			frappe.throw(_("Enable Google Meet before making it the default for internal meetings."))
		if self.internal_meeting_provider == "Zoom" and not self.zoom_enabled and self.google_meet_enabled:
			frappe.msgprint(_("Zoom is disabled; consider making Google Meet the default."), alert=True)

	def validate_google_key(self):
		key = self.google_service_account_key
		# An unchanged Password field comes back masked.
		if not key or set(key) == {"*"}:
			return
		try:
			info = json.loads(key)
		except ValueError:
			frappe.throw(_("The service account key must be the JSON key file downloaded from Google Cloud."))
		missing = {"type", "client_email", "private_key", "client_id"} - set(info)
		if info.get("type") != "service_account" or missing:
			frappe.throw(_("The JSON is not a service account key."))
