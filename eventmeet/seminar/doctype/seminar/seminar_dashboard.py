from frappe import _


def get_data():
	return {
		"fieldname": "seminar",
		"transactions": [
			{"label": _("Attendees"), "items": ["Seminar Registration", "Seminar Feedback"]},
		],
	}
