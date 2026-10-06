app_name = "eventmeet"
app_title = "EventMeet"
app_publisher = "Lifegence Corporation"
app_description = "Seminar & internal meeting management: registration, Stripe payments, Zoom / Google Meet, minutes and action items"
app_email = "contact@lifegence.com"
app_license = "MIT"

add_to_apps_screen = [
	{
		"name": app_name,
		"logo": "/assets/eventmeet/images/seminar-icon.svg",
		"title": "EventMeet",
		"route": "/app/eventmeet",
	},
]

app_include_js = ["/assets/eventmeet/js/conference.js"]

before_install = "eventmeet.install.before_install"
after_migrate = "eventmeet.install.ensure_roles"

permission_query_conditions = {
	"Internal Meeting": "eventmeet.meeting.doctype.internal_meeting.internal_meeting.get_permission_query_conditions",
}

has_permission = {
	"Internal Meeting": "eventmeet.meeting.doctype.internal_meeting.internal_meeting.has_permission",
}

doc_events = {
	"ToDo": {
		"on_update": "eventmeet.services.todo_sync.on_todo_update",
	},
}

scheduler_events = {
	"cron": {
		"*/10 * * * *": [
			"eventmeet.tasks.reconcile_pending_payments",
			"eventmeet.tasks.retry_missing_conference_registrations",
			"eventmeet.tasks.process_ended_conference_sessions",
		],
	},
	"hourly": [
		"eventmeet.tasks.send_seminar_reminders",
		"eventmeet.tasks.send_feedback_requests",
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
