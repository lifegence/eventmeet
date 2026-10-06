app_name = "eventmeet_theme_example"
app_title = "EventMeet Theme Example"
app_publisher = "Lifegence Corporation"
app_description = "Example theme app for EventMeet"
app_email = "contact@lifegence.com"
app_license = "MIT"

required_apps = ["eventmeet"]

# Replace EventMeet's page templates. Keys: seminar_list, seminar_detail, registration, feedback.
# Each template extends EventMeet's own and overrides only the blocks it needs.
eventmeet_website_templates = {
	"seminar_list": "eventmeet_theme_example/templates/eventmeet/seminar_list.html",
	"seminar_detail": "eventmeet_theme_example/templates/eventmeet/seminar_detail.html",
}
