import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

from eventmeet.conferencing.providers import ParticipantRecord
from eventmeet.meeting.doctype.internal_meeting.internal_meeting import (
	get_permission_query_conditions,
	has_permission,
)
from eventmeet.services import conference, notifications
from eventmeet.services.host_pool import allocate_host
from eventmeet.tests.utils import (
	SeminarTestCase,
	capture_mail,
	make_host,
	patch_providers,
	reset_conference_sessions,
)


def make_user(email: str, roles=("Desk User",)):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0].title(),
				"send_welcome_email": 0,
				"user_type": "System User",
				"roles": [{"role": role} for role in roles if frappe.db.exists("Role", role)],
			}
		).insert(ignore_permissions=True)
	return email


def make_meeting(organizer: str, attendees=(), online=1, **kwargs):
	starts_at = kwargs.pop("starts_at", add_to_date(now_datetime(), days=1))
	return frappe.get_doc(
		{
			"doctype": "Internal Meeting",
			"title": kwargs.pop("title", "Weekly sync"),
			"organizer": organizer,
			"starts_at": starts_at,
			"ends_at": add_to_date(starts_at, hours=1),
			"online": online,
			"attendees": [{"user": user} for user in attendees],
			"agenda": [{"topic": "Status"}, {"topic": "Risks"}],
			**kwargs,
		}
	).insert(ignore_permissions=True)


class TestHostPool(SeminarTestCase):
	def setUp(self):
		reset_conference_sessions()
		for name in frappe.get_all("Zoom Host Account", pluck="name"):
			frappe.db.set_value("Zoom Host Account", name, "enabled", 0)
		frappe.db.set_single_value("Conferencing Settings", "allocation_buffer_minutes", 15)
		self.fakes = patch_providers(self)
		self.provider = self.fakes["Zoom"]
		self.organizer = make_user("organizer@example.com")

	def test_prefers_smallest_sufficient_license(self):
		make_host("Big Webinar", webinar_capacity=1000)
		make_host("Small Webinar", webinar_capacity=500)
		start = get_datetime("2030-01-01 10:00:00")
		self.assertEqual(
			allocate_host("Webinar", start, add_to_date(start, hours=1), 300, "seminar"), "Small Webinar"
		)
		self.assertEqual(
			allocate_host("Webinar", start, add_to_date(start, hours=1), 800, "seminar"), "Big Webinar"
		)

	def test_respects_purpose_flags(self):
		make_host("Seminar Only", use_for_internal_meetings=0)
		start = get_datetime("2030-01-01 10:00:00")
		with self.assertRaises(frappe.ValidationError):
			allocate_host("Meeting", start, add_to_date(start, hours=1), 5, "internal")

	def test_overlapping_meetings_use_different_hosts_and_buffer_applies(self):
		make_host("Host A")
		make_host("Host B")
		start = get_datetime("2030-01-01 10:00:00")
		first = make_meeting(self.organizer, starts_at=start)
		second = make_meeting(self.organizer, starts_at=add_to_date(start, minutes=30))
		host = lambda m: frappe.db.get_value("Conference Session", m.conference_session, "host_account")  # noqa: E731
		self.assertNotEqual(host(first), host(second))

		# Both hosts are busy (10:00-11:00 and 10:30-11:30) plus a 15-minute buffer.
		with self.assertRaises(frappe.ValidationError):
			make_meeting(self.organizer, starts_at=add_to_date(start, minutes=70))
		third = make_meeting(self.organizer, starts_at=add_to_date(start, minutes=75))
		self.assertEqual(host(third), host(first))

	def test_cancelled_meeting_frees_host(self):
		make_host("Only Host")
		start = get_datetime("2030-01-02 10:00:00")
		first = make_meeting(self.organizer, starts_at=start)
		first.status = "Cancelled"
		first.save(ignore_permissions=True)
		second = make_meeting(self.organizer, starts_at=start)
		self.assertTrue(second.conference_session)


class TestInternalMeeting(SeminarTestCase):
	def setUp(self):
		reset_conference_sessions()
		self.mail = capture_mail(self)
		make_host("Internal Host")
		self.fakes = patch_providers(self)
		self.provider = self.fakes["Zoom"]
		self.organizer = make_user("organizer@example.com")
		self.member = make_user("member@example.com")
		self.outsider = make_user("outsider@example.com")

	def test_organizer_added_as_attendee_and_zoom_meeting_created(self):
		meeting = make_meeting(self.organizer, [self.member])
		self.assertEqual({row.user for row in meeting.attendees}, {self.organizer, self.member})
		self.assertTrue(meeting.join_url)
		spec = self.provider.called("create")[0][2]
		self.assertEqual((spec.kind, spec.registration_required), ("Meeting", False))
		self.assertIn("- Status", spec.agenda)

	def test_offline_meeting_has_no_session(self):
		meeting = make_meeting(self.organizer, online=0)
		self.assertFalse(meeting.conference_session)

	def test_duplicate_attendee_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			make_meeting(self.organizer, [self.member, self.member])

	def test_permissions(self):
		meeting = make_meeting(self.organizer, [self.member])
		self.assertTrue(has_permission(meeting, "write", self.organizer))
		self.assertTrue(has_permission(meeting, "read", self.member))
		self.assertFalse(has_permission(meeting, "delete", self.member))
		self.assertFalse(has_permission(meeting, "read", self.outsider))

		condition = get_permission_query_conditions(self.outsider)
		visible = frappe.db.sql(
			f"select name from `tabInternal Meeting` where name = %s and {condition}",  # nosemgrep: eventmeet-fstring-sql - condition is escaped
			meeting.name,
		)
		self.assertFalse(visible)
		condition = get_permission_query_conditions(self.member)
		visible = frappe.db.sql(
			f"select name from `tabInternal Meeting` where name = %s and {condition}",  # nosemgrep: eventmeet-fstring-sql - condition is escaped
			meeting.name,
		)
		self.assertTrue(visible)

	def test_action_items_sync_with_todo(self):
		meeting = make_meeting(self.organizer, [self.member])
		meeting.append("actions", {"description": "Draft proposal", "assigned_to": self.member})
		meeting.save(ignore_permissions=True)
		meeting.reload()
		todo_name = meeting.actions[0].todo
		self.assertTrue(todo_name)
		self.assertEqual(frappe.db.get_value("ToDo", todo_name, "allocated_to"), self.member)

		todo = frappe.get_doc("ToDo", todo_name)
		todo.status = "Closed"
		todo.save(ignore_permissions=True)
		self.assertEqual(
			frappe.db.get_value("Internal Meeting Action", meeting.actions[0].name, "status"), "Closed"
		)

		meeting.reload()
		meeting.actions = []
		meeting.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("ToDo", todo_name, "status"), "Closed")

	def test_removed_open_action_cancels_todo(self):
		meeting = make_meeting(self.organizer, [self.member])
		meeting.append("actions", {"description": "Book room", "assigned_to": self.member})
		meeting.save(ignore_permissions=True)
		meeting.reload()
		todo_name = meeting.actions[0].todo
		meeting.actions = []
		meeting.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("ToDo", todo_name, "status"), "Cancelled")

	def test_attendance_and_summary(self):
		meeting = make_meeting(self.organizer, [self.member])
		self.provider.participants = [ParticipantRecord("Member", "member@example.com", None, None, 42)]
		self.provider.summary = "<p>Decided X</p>"
		conference.sync_attendance(meeting.conference_session)
		self.assertTrue(conference.import_summary(meeting.conference_session))
		meeting.reload()
		attended = {row.user: (row.attended, row.attended_minutes) for row in meeting.attendees}
		self.assertEqual(attended[self.member], (1, 42))
		self.assertEqual(attended[self.organizer][0], 0)
		self.assertEqual(meeting.ai_summary, "<p>Decided X</p>")
		self.assertEqual(meeting.minutes, "<p>Decided X</p>", "empty minutes are prefilled with the summary")

	def test_invitation_ics(self):
		meeting = make_meeting(self.organizer, [self.member], title="Plan; Q4, budget")
		ics = notifications.meeting_ics(meeting)
		self.assertIn("SUMMARY:Plan\\; Q4\\, budget", ics)
		self.assertIn("mailto:member@example.com", ics)
		self.assertIn("METHOD:REQUEST", ics)
		meeting.send_invitations()
		self.assertEqual(frappe.db.get_value("Internal Meeting", meeting.name, "status"), "Invited")
		self.assertEqual(self.mail[0]["attachments"][0]["fname"], "invite.ics")
		self.assertIn(meeting.join_url, self.mail[0]["rendered"])
		self.assertIn("Plan; Q4, budget", self.mail[0]["rendered"])


class TestExternalAttendees(SeminarTestCase):
	def setUp(self):
		reset_conference_sessions()
		self.mail = capture_mail(self)
		make_host("Internal Host")
		self.fakes = patch_providers(self)
		self.organizer = make_user("organizer@example.com")
		self.member = make_user("member@example.com")

	def meeting_with_guest(self, **kwargs):
		return make_meeting(
			self.organizer,
			[self.member],
			external_attendees=[
				{"guest_name": "Nomura (Guest)", "email": " Guest@Partner.test ", "organization": "Partner"}
			],
			**kwargs,
		)

	def test_guest_is_normalized_and_invited_without_desk_link(self):
		meeting = self.meeting_with_guest()
		self.assertEqual(meeting.external_attendees[0].email, "guest@partner.test")
		self.assertIn("guest@partner.test", [i.email for i in meeting.invitees()])

		meeting.send_invitations()
		by_recipient = {tuple(m["recipients"]): m for m in self.mail}
		external = by_recipient[("guest@partner.test",)]
		internal = next(m for key, m in by_recipient.items() if self.member in key)
		self.assertNotIn("guest@partner.test", internal["recipients"], "guests get a separate email")
		self.assertNotIn("Open in Frappe", external["rendered"], "no desk link for guests")
		self.assertIn("Open in Frappe", internal["rendered"])
		self.assertIn(meeting.join_url, external["rendered"])
		ics = external["attachments"][0]["fcontent"].decode()
		self.assertIn("CN=Nomura (Guest):mailto:guest@partner.test", ics)

	def test_guest_validation(self):
		with self.assertRaises(frappe.ValidationError):
			make_meeting(
				self.organizer, [], external_attendees=[{"guest_name": "X", "email": "not-an-email"}]
			)
		with self.assertRaises(frappe.ValidationError):
			make_meeting(
				self.organizer,
				[],
				external_attendees=[
					{"guest_name": "A", "email": "a@partner.test"},
					{"guest_name": "A2", "email": "A@partner.test"},
				],
			)
		with self.assertRaises(frappe.ValidationError):
			make_meeting(
				self.organizer, [self.member], external_attendees=[{"guest_name": "M", "email": self.member}]
			)

	def test_guest_attendance_is_recorded(self):
		meeting = self.meeting_with_guest()
		self.fakes["Zoom"].participants = [ParticipantRecord("Nomura", "guest@partner.test", None, None, 33)]
		conference.sync_attendance(meeting.conference_session)
		meeting.reload()
		self.assertEqual(
			(meeting.external_attendees[0].attended, meeting.external_attendees[0].attended_minutes), (1, 33)
		)
