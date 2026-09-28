import frappe
from frappe import _
from frappe.utils import now_datetime

no_cache = 1


def get_context(context):
	context.title = _("Seminars")
	context.seminars = frappe.get_all(
		"Seminar",
		filters={"published": 1, "status": ["in", ["Open", "Closed"]], "ends_at": [">=", now_datetime()]},
		fields=[
			"name",
			"title",
			"summary",
			"format",
			"starts_at",
			"ends_at",
			"banner_image",
			"route",
			"status",
			"venue",
		],
		order_by="starts_at asc",
		limit=100,
	)
	return context
