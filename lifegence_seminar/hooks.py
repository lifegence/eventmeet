app_name = "lifegence_seminar"
app_title = "Lifegence Seminar"
app_publisher = "Lifegence"
app_description = "Seminar planning & operation (online/offline) and internal meetings with Zoom and Stripe"
app_email = "info@lifegence.com"
app_license = "Lifegence Proprietary License"

add_to_apps_screen = [
	{
		"name": app_name,
		"logo": "/assets/lifegence_seminar/images/seminar-icon.svg",
		"title": "Seminar",
		"route": "/app/seminar",
	},
]

app_include_js = ["/assets/lifegence_seminar/js/conference.js"]

before_install = "lifegence_seminar.install.before_install"
after_migrate = "lifegence_seminar.install.ensure_roles"

permission_query_conditions = {
	"Internal Meeting": "lifegence_seminar.meeting.doctype.internal_meeting.internal_meeting.get_permission_query_conditions",
}

has_permission = {
	"Internal Meeting": "lifegence_seminar.meeting.doctype.internal_meeting.internal_meeting.has_permission",
}

doc_events = {
	"ToDo": {
		"on_update": "lifegence_seminar.services.todo_sync.on_todo_update",
	},
}

scheduler_events = {
	"cron": {
		"*/10 * * * *": [
			"lifegence_seminar.tasks.reconcile_pending_payments",
			"lifegence_seminar.tasks.retry_missing_conference_registrations",
			"lifegence_seminar.tasks.process_ended_conference_sessions",
		],
	},
	"hourly": [
		"lifegence_seminar.tasks.send_seminar_reminders",
		"lifegence_seminar.tasks.send_feedback_requests",
	],
}

user_data_fields = [
	{
		"doctype": "Seminar Registration",
		"filter_by": "email",
		"redact_fields": ["attendee_name", "company", "phone"],
		"partial": 1,
	},
]
