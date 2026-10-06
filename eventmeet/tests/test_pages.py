"""Render the public pages (guest) to catch template/context errors."""

from unittest.mock import patch

import frappe
from frappe.utils import add_to_date, now_datetime

from eventmeet import website
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

	def test_seminar_banner_does_not_replace_the_site_logo(self):
		frappe.db.set_value("Seminar", self.seminar.name, "banner_image", "/files/seminar-banner.png")
		status, html = render(self.seminar.route)
		self.assertEqual(status, 200)
		self.assertIn('class="ls-banner" src="/files/seminar-banner.png"', html)
		self.assertNotIn("<img src='/files/seminar-banner.png'>", html, "navbar logo")

	def test_feedback_page_shows_form_after_start(self):
		frappe.db.set_value("Seminar", self.seminar.name, "starts_at", add_to_date(now_datetime(), hours=-1))
		status, html = render("seminar-feedback", token=self.token)
		self.assertEqual(status, 200)
		self.assertIn("ls-feedback-form", html)
		self.assertIn(f'"{self.token}"', html)


class TestWebsiteDesign(SeminarTestCase):
	def setUp(self):
		self.seminar = make_seminar(title="Design Test")
		self.addCleanup(self.reset_settings)

	def reset_settings(self):
		for field, value in (
			("website_design", "Standard"),
			("website_custom_css", ""),
			("website_header_html", ""),
			("website_footer_html", ""),
		):
			frappe.db.set_single_value("Seminar Settings", field, value)
		frappe.clear_document_cache("Seminar Settings", "Seminar Settings")

	def configure(self, **values):
		settings = frappe.get_single("Seminar Settings")
		settings.update(values)
		settings.save(ignore_permissions=True)

	def test_design_css_and_sanitized_html(self):
		self.configure(
			website_design="Custom",
			website_custom_css=".em-page { --em-primary: #13579b; } </style><script>alert(1)</script>",
			website_header_html='<p class="notice">Early bird ends Friday</p><script>alert(2)</script>',
			website_footer_html='<a href="/contact" onclick="alert(3)">Contact</a>',
		)
		for path in ("seminars", self.seminar.route):
			with self.subTest(path=path):
				status, html = render(path)
				self.assertEqual(status, 200)
				self.assertIn("em-design-custom", html)
				self.assertIn("--em-primary: #13579b", html)
				self.assertIn("Early bird ends Friday", html)
				self.assertIn('href="/contact"', html)
				self.assertNotIn("alert(1)</script>", html)
				# No executable script. (Frappe v15 already escapes it to text when the settings are saved.)
				self.assertNotIn("<script>alert(2)", html)
				self.assertNotIn("onclick", html)

	def test_custom_css_only_with_the_custom_design(self):
		self.configure(website_design="Friendly", website_custom_css=".em-page { --em-primary: #13579b; }")
		status, html = render("seminars")
		self.assertEqual(status, 200)
		self.assertIn("em-design-friendly", html)
		self.assertNotIn("--em-primary: #13579b", html, "kept in the settings, not applied")
		self.configure(website_design="Custom")
		self.assertIn("--em-primary: #13579b", render("seminars")[1])

	def test_patch_moves_standard_with_css_to_custom(self):
		from eventmeet.patches.v0_2 import use_custom_design_for_custom_css

		frappe.db.set_single_value("Seminar Settings", "website_design", "Standard")
		frappe.db.set_single_value("Seminar Settings", "website_custom_css", ".em-page { --em-radius: 0; }")
		use_custom_design_for_custom_css.execute()
		self.assertEqual(frappe.db.get_single_value("Seminar Settings", "website_design"), "Custom")

	def test_unknown_design_falls_back_to_standard(self):
		frappe.db.set_single_value("Seminar Settings", "website_design", "Nope")
		frappe.clear_document_cache("Seminar Settings", "Seminar Settings")
		self.assertEqual(website.get_design().design, "standard")

	def test_template_override_from_hook(self):
		original = frappe.get_hooks

		def get_hooks(hook=None, *args, **kwargs):
			if hook == "eventmeet_website_templates":
				return {"seminar_list": ["eventmeet/tests/fixtures/custom_seminar_list.html"]}
			return original(hook, *args, **kwargs)

		with patch("frappe.get_hooks", side_effect=get_hooks):
			status, html = render("seminars")
		self.assertEqual(status, 200)
		self.assertIn('id="custom-list-header"', html)
		self.assertIn('<div class="custom-card">Design Test</div>', html)
		self.assertIn("em-design-standard", html, "the layout of EventMeet is kept")

	def test_safe_html_removes_scripts_with_their_content(self):
		html = website.safe_html('<p>Hi</p><script>alert(1)</script><img src="x.png" onerror="alert(2)">')
		self.assertIn("<p>Hi</p>", html)
		self.assertNotIn("alert", html)
		self.assertNotIn("script", html)

	def test_safe_css_cannot_close_the_style_element(self):
		self.assertNotIn("</style", website.safe_css("a{} </style><script>x</script>"))
