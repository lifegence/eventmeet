"""Design of the public seminar pages: built-in designs, custom CSS / HTML, and template overrides.

Templates can be replaced by another installed app (not from the database) through the hook

	eventmeet_website_templates = {"seminar_list": "my_app/templates/eventmeet/seminar_list.html"}

so that only code that is deployed to the bench is ever rendered as a Jinja template.
"""

from __future__ import annotations

import frappe
from frappe.utils.html_utils import sanitize_html

TEMPLATES = {
	"seminar_list": "eventmeet/templates/eventmeet/seminar_list.html",
	"seminar_detail": "eventmeet/templates/eventmeet/seminar_detail.html",
	"registration": "eventmeet/templates/eventmeet/registration.html",
	"feedback": "eventmeet/templates/eventmeet/feedback.html",
}
DESIGNS = ("Standard", "Corporate", "Friendly", "Minimal")


def get_template(key: str) -> str:
	"""Template path for a page; the last installed app that overrides it wins."""
	overrides = frappe.get_hooks("eventmeet_website_templates") or {}
	paths = overrides.get(key) or []
	if isinstance(paths, str):
		paths = [paths]
	return paths[-1] if paths else TEMPLATES[key]


def safe_css(css: str | None) -> str:
	# The CSS is placed inside a <style> element: never let it close the element.
	return (css or "").replace("</", "<\\/")


def safe_html(html: str | None) -> str:
	"""Sanitize HTML from the settings: remove script-like elements with their content, then sanitize.

	Frappe v15 escapes disallowed tags instead of removing them, which would show the code as text.
	"""
	from bs4 import BeautifulSoup

	if not html:
		return ""
	soup = BeautifulSoup(html, "html.parser")
	for element in soup(["script", "style", "iframe", "object", "embed", "noscript", "template"]):
		element.decompose()
	return sanitize_html(str(soup), always_sanitize=True)


def get_design() -> frappe._dict:
	settings = frappe.get_cached_doc("Seminar Settings")
	design = settings.get("website_design") or "Standard"
	return frappe._dict(
		design=(design if design in DESIGNS else "Standard").lower(),
		custom_css=safe_css(settings.get("website_custom_css")),
		# Sanitized: scripts and event handlers are removed, and the HTML is not run as a template.
		header_html=safe_html(settings.get("website_header_html")),
		footer_html=safe_html(settings.get("website_footer_html")),
	)


def apply(context, page: str):
	"""Add the design and the page template (`em.template`) to a page context."""
	context.em = get_design()
	context.em.template = get_template(page)
	return context
