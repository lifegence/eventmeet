"""Render the public pages (guest) to catch template/context errors."""

from unittest.mock import patch

import frappe
from frappe.utils import add_to_date, now_datetime

from eventmeet.services import registration as reg_service
from eventmeet.tests.utils import SeminarTestCase, make_seminar


def render(path: str, **query) -> tuple[int, str]:
	"""Render like a real request (Frappe's own website tests use set_request)."""
	from urllib.parse import urlencode

	from frappe.utils import set_request
	from frappe.website.serve import get_response

	frappe.set_user("Guest")
	try:
		set_request(method="GET", path=f"/{path}" + (f"?{urlencode(query)}" if query else ""))
		frappe.local.form_dict = frappe._dict(query)
		response = get_response()
		return response.status_code, response.get_data(as_text=True)
	finally:
		frappe.set_user("Administrator")


class TestPublicPages(SeminarTestCase):
	def setUp(self):
		with patch("frappe.sendmail"):
			self.seminar = make_seminar(title="Page Test")
			result = reg_service.create_registration(
				self.seminar.name, "General", "Hanako", "hanako@example.com"
			)
		self.token = result["redirect_url"].split("token=")[1]

	def test_pages_render_for_valid_and_invalid_tokens(self):
		for path, query in (
			("seminars", {}),
			(self.seminar.route, {}),
			("seminar-registration", {"token": self.token}),
			("seminar-registration", {"token": "bogus"}),
			("seminar-feedback", {"token": self.token}),
			("seminar-feedback", {"token": "bogus"}),
		):
			with self.subTest(path=path, query=query):
				status, _html = render(path, **query)
				self.assertEqual(status, 200)

	def test_feedback_page_shows_form_after_start(self):
		frappe.db.set_value("Seminar", self.seminar.name, "starts_at", add_to_date(now_datetime(), hours=-1))
		status, html = render("seminar-feedback", token=self.token)
		self.assertEqual(status, 200)
		self.assertIn("ls-feedback-form", html)
		self.assertIn(f'"{self.token}"', html)
