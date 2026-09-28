import datetime
import json
from unittest.mock import patch

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

from lifegence_seminar.conferencing.providers import ConferenceSpec, Invitee, ParticipantRecord, SessionRef
from lifegence_seminar.conferencing.providers.google_meet import (
	GoogleMeetProvider,
	parse_rfc3339,
	to_rfc3339_utc,
)
from lifegence_seminar.services import conference
from lifegence_seminar.tests.test_internal_meeting import make_meeting, make_user
from lifegence_seminar.tests.utils import (
	SeminarTestCase,
	capture_mail,
	make_host,
	patch_providers,
	reset_conference_sessions,
)


def tokyo(fn):
	"""Pin the system time zone (both the frappe.utils.data lookup and the provider's own import)."""
	fn = patch("frappe.utils.data.get_system_timezone", return_value="Asia/Tokyo")(fn)
	return patch(
		"lifegence_seminar.conferencing.providers.google_meet.get_system_timezone", return_value="Asia/Tokyo"
	)(fn)


class FakeGoogleClient:
	"""Records requests and answers from a routing table of (method, url-suffix) -> response."""

	def __init__(self, routes):
		self.routes = routes
		self.requests = []

	def request(
		self, subject, scopes, method, url, *, params=None, json_body=None, allow_missing=False, raw=False
	):
		self.requests.append(
			{
				"subject": subject,
				"scopes": scopes,
				"method": method,
				"url": url,
				"params": params,
				"json": json_body,
			}
		)
		for (route_method, suffix), response in self.routes.items():
			if route_method == method and url.endswith(suffix):
				return response(params) if callable(response) else response
		raise AssertionError(f"unexpected request {method} {url}")


def spec(**overrides):
	values = {
		"topic": "Weekly sync",
		"kind": "Meeting",
		"starts_at": datetime.datetime(2026, 10, 1, 14, 0),
		"duration_minutes": 60,
		"timezone": "Asia/Tokyo",
		"agenda": "- Status",
		"attendees": [Invitee("a@example.com"), Invitee("b@example.com", optional=True)],
	}
	values.update(overrides)
	return ConferenceSpec(**values)


class TestGoogleMeetProvider(SeminarTestCase):
	def test_create_event_with_meet_link(self):
		client = FakeGoogleClient(
			{
				("POST", "/calendars/primary/events"): {
					"id": "evt1",
					"hangoutLink": "https://meet.google.com/abc-defg-hij",
					"conferenceData": {"conferenceId": "abc-defg-hij"},
				}
			}
		)
		created = GoogleMeetProvider(client).create("organizer@example.com", spec())
		self.assertEqual(
			(created.external_id, created.join_url, created.meeting_code),
			("evt1", "https://meet.google.com/abc-defg-hij", "abc-defg-hij"),
		)
		sent = client.requests[0]
		self.assertEqual(sent["subject"], "organizer@example.com", "impersonates the organizer")
		self.assertEqual(sent["params"], {"conferenceDataVersion": 1, "sendUpdates": "none"})
		body = sent["json"]
		self.assertEqual(body["start"], {"dateTime": "2026-10-01T14:00:00", "timeZone": "Asia/Tokyo"})
		self.assertEqual(body["end"]["dateTime"], "2026-10-01T15:00:00")
		self.assertEqual(body["attendees"][1], {"email": "b@example.com", "optional": True})
		self.assertEqual(
			body["conferenceData"]["createRequest"]["conferenceSolutionKey"], {"type": "hangoutsMeet"}
		)

	@patch("lifegence_seminar.conferencing.providers.google_meet.time.sleep")
	def test_create_waits_for_pending_conference(self, _sleep):
		client = FakeGoogleClient(
			{
				("POST", "/calendars/primary/events"): {"id": "evt2", "conferenceData": {}},
				("GET", "/events/evt2"): {
					"id": "evt2",
					"hangoutLink": "https://meet.google.com/xyz",
					"conferenceData": {"conferenceId": "xyz"},
				},
			}
		)
		created = GoogleMeetProvider(client).create("o@example.com", spec())
		self.assertEqual(created.join_url, "https://meet.google.com/xyz")

	def test_update_and_delete_notify_flags(self):
		client = FakeGoogleClient({("PATCH", "/events/evt1"): {}, ("DELETE", "/events/evt1"): None})
		provider = GoogleMeetProvider(client)
		ref = SessionRef("Meeting", "evt1", host="o@example.com")
		provider.update(ref, spec(notify=True))
		provider.delete(ref, notify=False)
		self.assertEqual(client.requests[0]["params"]["sendUpdates"], "all")
		self.assertEqual(client.requests[1]["params"], {"sendUpdates": "none"})

	@tokyo
	def test_participants_with_sessions_and_email_lookup(self, *_tz):
		frappe.cache.delete_value("lifegence_seminar:gmeet_email:111")
		client = FakeGoogleClient(
			{
				("GET", "/v2/conferenceRecords"): {"conferenceRecords": [{"name": "conferenceRecords/r1"}]},
				("GET", "/conferenceRecords/r1/participants"): {
					"participants": [
						{
							"name": "conferenceRecords/r1/participants/p1",
							"earliestStartTime": "2026-10-01T05:00:00.123456789Z",
							"latestEndTime": "2026-10-01T05:50:00Z",
							"signedinUser": {"user": "users/111", "displayName": "Alice"},
						},
						{
							"name": "conferenceRecords/r1/participants/p2",
							"anonymousUser": {"displayName": "Guest Bob"},
						},
					]
				},
				("GET", "/participants/p1/participantSessions"): {
					"participantSessions": [
						{"startTime": "2026-10-01T05:00:00Z", "endTime": "2026-10-01T05:20:00Z"},
						{"startTime": "2026-10-01T05:30:00Z", "endTime": "2026-10-01T05:50:00Z"},
					]
				},
				("GET", "/participants/p2/participantSessions"): {"participantSessions": []},
				("GET", "/people/111"): {
					"emailAddresses": [
						{"value": "alias@example.com"},
						{"value": "Alice@Example.com", "metadata": {"primary": True}},
					]
				},
			}
		)
		ref = SessionRef(
			"Meeting",
			"evt1",
			host="o@example.com",
			meeting_code="abc-defg-hij",
			starts_at=datetime.datetime(2026, 10, 1, 14, 0),
			ends_at=datetime.datetime(2026, 10, 1, 15, 0),
		)
		records = GoogleMeetProvider(client).list_participants(ref)
		self.assertEqual(records[0].email, "alice@example.com")
		self.assertEqual(records[0].duration_minutes, 40.0, "sums sessions, excluding the break")
		self.assertEqual(records[0].join_time, datetime.datetime(2026, 10, 1, 14, 0, 0, 123456))
		self.assertEqual((records[1].name, records[1].email), ("Guest Bob", ""))
		record_filter = client.requests[0]["params"]["filter"]
		self.assertIn('space.meeting_code = "abc-defg-hij"', record_filter)
		self.assertIn('start_time >= "2026-10-01T03:00:00Z"', record_filter)

		# Email lookups are cached.
		GoogleMeetProvider(client).list_participants(ref)
		self.assertEqual(sum(1 for r in client.requests if "/people/" in r["url"]), 1)

	def test_no_conference_record_yet_raises_for_retry(self):
		from lifegence_seminar.conferencing.providers import ConferenceProviderError

		client = FakeGoogleClient({("GET", "/v2/conferenceRecords"): {}})
		with self.assertRaises(ConferenceProviderError):
			GoogleMeetProvider(client).list_participants(SessionRef("Meeting", "e", "o@x.com", "code"))

	def test_meeting_notes_are_sanitized(self):
		client = FakeGoogleClient(
			{
				("GET", "/v2/conferenceRecords"): {"conferenceRecords": [{"name": "conferenceRecords/r1"}]},
				("GET", "/conferenceRecords/r1/smartNotes"): {
					"smartNotes": [
						{"state": "STARTED", "docsDestination": {"document": "draft"}},
						{"state": "FILE_GENERATED", "docsDestination": {"document": "doc1"}},
					]
				},
				(
					"GET",
					"/files/doc1/export",
				): "<html><body><h1>Notes</h1><script>x()</script><p>Decided</p></body></html>",
			}
		)
		ref = SessionRef("Meeting", "evt1", "o@example.com", "abc")
		self.assertIsNone(GoogleMeetProvider(client, import_notes=False).get_summary_html(ref))
		html = GoogleMeetProvider(client, import_notes=True).get_summary_html(ref)
		self.assertIn("<h1>Notes</h1>", html)
		self.assertIn("Decided", html)
		self.assertNotIn("<script>", html)
		self.assertFalse(any("/files/draft" in r["url"] for r in client.requests))

	@tokyo
	def test_time_helpers(self, *_tz):
		self.assertEqual(parse_rfc3339("2026-10-01T05:00:00Z"), datetime.datetime(2026, 10, 1, 14, 0))
		self.assertEqual(parse_rfc3339("2026-10-01T14:00:00+09:00"), datetime.datetime(2026, 10, 1, 14, 0))
		self.assertIsNone(parse_rfc3339("garbage"))
		self.assertEqual(to_rfc3339_utc(datetime.datetime(2026, 10, 1, 14, 0)), "2026-10-01T05:00:00Z")


class TestConferencingSettings(SeminarTestCase):
	def test_rejects_non_service_account_key(self):
		settings = frappe.get_single("Conferencing Settings")
		settings.google_meet_enabled = 1
		settings.google_workspace_domains = "example.com"
		settings.google_service_account_key = json.dumps({"type": "authorized_user"})
		with self.assertRaises(frappe.ValidationError):
			settings.save()

	def test_google_default_requires_google_enabled(self):
		settings = frappe.get_single("Conferencing Settings")
		settings.google_meet_enabled = 0
		settings.internal_meeting_provider = "Google Meet"
		with self.assertRaises(frappe.ValidationError):
			settings.save()


class TestInternalMeetingWithGoogleMeet(SeminarTestCase):
	def setUp(self):
		reset_conference_sessions()
		frappe.db.set_single_value("Conferencing Settings", "google_workspace_domains", "example.com")
		frappe.db.set_single_value("Conferencing Settings", "internal_meeting_provider", "Google Meet")
		self.mail = capture_mail(self)
		self.fakes = patch_providers(self)
		self.google = self.fakes["Google Meet"]
		self.organizer = make_user("organizer@example.com")
		self.member = make_user("member@example.com")

	def test_meeting_is_created_in_organizer_calendar_without_host_pool(self):
		for name in frappe.get_all("Zoom Host Account", pluck="name"):
			frappe.db.set_value("Zoom Host Account", name, "enabled", 0)
		meeting = make_meeting(self.organizer, [self.member])
		self.assertEqual(meeting.conference_provider, "Google Meet")
		self.assertTrue(meeting.join_url.startswith("https://meet.test/"))
		session = frappe.get_doc("Conference Session", meeting.conference_session)
		self.assertEqual(
			(session.provider, session.host_user, session.host_account), ("Google Meet", self.organizer, None)
		)
		self.assertTrue(session.meeting_code)

		_action, host, created_spec = self.google.called("create")[0]
		self.assertEqual(host, self.organizer)
		self.assertEqual(
			[i.email for i in created_spec.attendees], [self.member], "organizer is not an invitee"
		)
		self.assertFalse(created_spec.notify, "no Google invitation before 'Send Invitation'")

	def test_organizer_outside_workspace_domain_is_rejected(self):
		outsider = make_user("someone@other.test")
		with self.assertRaises(frappe.ValidationError):
			make_meeting(outsider, [self.member])

	def test_invitations_are_sent_by_google_and_changes_notified_afterwards(self):
		meeting = make_meeting(self.organizer, [self.member])
		meeting.save(ignore_permissions=True)
		self.assertFalse(
			self.google.called("update")[-1][2].notify, "attendee sync before invitation is silent"
		)

		self.assertEqual(meeting.send_invitations(), "google")
		self.assertTrue(self.google.called("update")[-1][2].notify)
		self.assertEqual(self.mail, [], "no duplicate ICS email for Google meetings")
		meeting.reload()
		self.assertEqual((meeting.status, meeting.invitations_sent), ("Invited", 1))

		meeting.starts_at = add_to_date(meeting.starts_at, hours=1)
		meeting.ends_at = add_to_date(meeting.ends_at, hours=1)
		meeting.save(ignore_permissions=True)
		self.assertTrue(self.google.called("update")[-1][2].notify, "reschedule after invitation notifies")

		meeting.status = "Cancelled"
		meeting.save(ignore_permissions=True)
		self.assertEqual(self.google.called("delete")[-1][2], True, "cancellation notifies via Google")

	def test_switching_provider_replaces_session(self):
		make_host("Internal Host")
		meeting = make_meeting(self.organizer, [self.member], conference_provider="Zoom")
		zoom_session = meeting.conference_session
		meeting.conference_provider = "Google Meet"
		meeting.save(ignore_permissions=True)
		meeting.reload()
		self.assertEqual(frappe.db.get_value("Conference Session", zoom_session, "status"), "Cancelled")
		self.assertEqual(
			frappe.db.get_value("Conference Session", meeting.conference_session, "provider"), "Google Meet"
		)

	def test_attendance_falls_back_to_display_name(self):
		meeting = make_meeting(self.organizer, [self.member])
		member_name = frappe.db.get_value(
			"Internal Meeting Attendee", {"parent": meeting.name, "user": self.member}, "full_name"
		)
		self.google.participants = [
			ParticipantRecord(member_name, "", None, None, 25),
			ParticipantRecord("Organizer", self.organizer, None, None, 60),
		]
		conference.sync_attendance(meeting.conference_session)
		meeting.reload()
		minutes = {row.user: row.attended_minutes for row in meeting.attendees}
		self.assertEqual(minutes, {self.organizer: 60, self.member: 25})

	def test_seminars_still_use_zoom(self):
		from lifegence_seminar.tests.utils import make_seminar

		make_host("Seminar Host", webinar_capacity=500)
		seminar = make_seminar(fmt="Online", conference_kind="Webinar")
		self.assertEqual(
			frappe.db.get_value("Conference Session", seminar.conference_session, "provider"), "Zoom"
		)

	def test_google_rejects_registration_sessions(self):
		with self.assertRaises(frappe.ValidationError):
			conference.schedule_session(
				frappe._dict(doctype="Seminar", name="x"),
				topic="t",
				starts_at=get_datetime(add_to_date(now_datetime(), days=3)),
				ends_at=get_datetime(add_to_date(now_datetime(), days=3, hours=1)),
				kind="Meeting",
				registration_required=True,
				expected_attendees=10,
				purpose="seminar",
				provider_name="Google Meet",
				organizer_email=self.organizer,
			)

	def test_existing_session_keeps_its_tool_when_default_changes(self):
		make_host("Internal Host")
		frappe.db.set_single_value("Conferencing Settings", "internal_meeting_provider", "Zoom")
		meeting = make_meeting(self.organizer, [self.member])
		zoom_session = meeting.conference_session
		frappe.db.set_value("Internal Meeting", meeting.name, "conference_provider", "")  # legacy row
		frappe.db.set_single_value("Conferencing Settings", "internal_meeting_provider", "Google Meet")

		meeting = frappe.get_doc("Internal Meeting", meeting.name)
		meeting.title = "Renamed"
		meeting.save(ignore_permissions=True)
		self.assertEqual(meeting.conference_provider, "Zoom")
		self.assertEqual(meeting.conference_session, zoom_session)
		self.assertEqual(frappe.db.get_value("Conference Session", zoom_session, "status"), "Scheduled")
