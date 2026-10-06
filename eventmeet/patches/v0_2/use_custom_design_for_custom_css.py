import frappe


def execute():
	"""Custom CSS now applies only to the "Custom" design; keep sites that used Standard + CSS unchanged."""
	css = frappe.db.get_single_value("Seminar Settings", "website_custom_css")
	design = frappe.db.get_single_value("Seminar Settings", "website_design") or "Standard"
	if (css or "").strip() and design == "Standard":
		frappe.db.set_single_value("Seminar Settings", "website_design", "Custom")
