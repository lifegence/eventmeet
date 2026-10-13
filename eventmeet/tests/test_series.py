import frappe
from frappe.utils import get_datetime

from eventmeet.meeting import series
from eventmeet.tests.test_internal_meeting import make_meeting, make_user
from eventmeet.tests.utils import (
	SeminarTestCase,
	capture_mail,
	make_host,
	patch_providers,
	reset_conference_sessions,
)


def starts(first, frequency, **kwargs):
	return [str(start) for start in series.occurrence_starts(first, frequency, **kwargs)]


class TestOccurrenceDates(SeminarTestCase):
	def test_weekly_and_every_two_weeks(self):
		# 2030-01-07 is a Monday.
		self.assertEqual(
			starts("2030-01-07 10:00:00", "Weekly", count=3),
			["2030-01-14 10:00:00", "2030-01-21 10:00:00"],
		)
		self.assertEqual(
			starts("2030-01-07 10:00:00", "Every 2 Weeks", until="2030-02-04"),
			["2030-01-21 10:00:00", "2030-02-04 10:00:00"],
		)

	def test_weekdays_skip_the_weekend(self):
		# Friday -> Monday, Tuesday.
		self.assertEqual(
			starts("2030-01-11 09:00:00", "Weekdays", count=3),
			["2030-01-14 09:00:00", "2030-01-15 09:00:00"],
		)

	def test_monthly_same_date_clamps_to_month_end(self):
		self.assertEqual(
			starts("2030-01-31 10:00:00", "Monthly (same date)", count=3),
			["2030-02-28 10:00:00", "2030-03-31 10:00:00"],
		)

	def test_monthly_same_weekday(self):
		# 2030-01-08 is the 2nd Tuesday; 2030-01-29 is the last (5th) Tuesday.
		self.assertEqual(
			starts("2030-01-08 10:00:00", "Monthly (same weekday)", count=3),
			["2030-02-12 10:00:00", "2030-03-12 10:00:00"],
		)
		self.assertEqual(
			starts("2030-01-29 10:00:00", "Monthly (same weekday)", count=2), ["2030-02-26 10:00:00"]
		)

	def test_limits(self):
		with self.assertRaises(frappe.ValidationError):
			series.occurrence_starts("2030-01-07 10:00:00", "Weekly")
		with self.assertRaises(frappe.ValidationError):
			series.occurrence_starts("2030-01-07 10:00:00", "Weekly", count=series.MAX_OCCURRENCES + 1)
		with self.assertRaises(frappe.ValidationError):
			series.occurrence_starts("2030-01-07 10:00:00", "Weekdays", until="2031-01-01")
		self.assertEqual(
			len(series.occurrence_starts("2030-01-07 10:00:00", "Weekly", count=series.MAX_OCCURRENCES)),
			series.MAX_OCCURRENCES - 1,
		)


class TestMeetingSeries(SeminarTestCase):
	def setUp(self):
		reset_conference_sessions()
		self.mail = capture_mail(self)
		make_host("Series Host")
		self.fakes = patch_providers(self)
		self.zoom = self.fakes["Zoom"]
		self.organizer = make_user("organizer@example.com")
		self.member = make_user("member@example.com")
		self.other = make_user("other@example.com")
		frappe.set_user(self.organizer)
		self.addCleanup(frappe.set_user, "Administrator")

	def make_series(self, count=3, **kwargs):
		first = make_meeting(
			self.organizer,
			[self.member],
			starts_at=get_datetime("2030-03-04 10:00:00"),
			conference_provider="Zoom",
			external_attendees=[{"guest_name": "Guest", "email": "guest@partner.test"}],
			**kwargs,
		)
		first.invitation_message = first.build_invitation_message()
		first.save()
		names = first.create_repeats("Weekly", count=count)
		first.reload()
		return first, [frappe.get_doc("Internal Meeting", name) for name in names]

	def test_repeat_creates_separate_meetings(self):
		first, others = self.make_series()
		self.assertEqual(first.series, first.name)
		self.assertEqual([str(m.starts_at) for m in others], ["2030-03-11 10:00:00", "2030-03-18 10:00:00"])
		for meeting in others:
			self.assertEqual(meeting.series, first.name)
			self.assertEqual(meeting.status, "Planned")
			self.assertEqual(str(get_datetime(meeting.ends_at)), str(meeting.starts_at).replace("10:", "11:"))
			self.assertEqual({row.user for row in meeting.attendees}, {self.organizer, self.member})
			self.assertEqual([row.email for row in meeting.external_attendees], ["guest@partner.test"])
			self.assertEqual([row.topic for row in meeting.agenda], ["Status", "Risks"])
			self.assertTrue(meeting.conference_session)
			self.assertNotEqual(meeting.conference_session, first.conference_session)
			# The invitation message shows each meeting's own date.
			self.assertIn(
				series.date_range_text(meeting.starts_at, meeting.ends_at), meeting.invitation_message
			)
			self.assertNotIn("2030-03-04", meeting.invitation_message)
		self.assertEqual(self.mail, [], "no invitation unless asked")

		with self.assertRaises(frappe.ValidationError):
			first.create_repeats("Weekly", count=2)

	def test_repeat_can_send_invitations(self):
		first = make_meeting(self.organizer, [self.member], conference_provider="Zoom")
		first.create_repeats("Weekly", count=2, send_invitations=1)
		second = frappe.get_all(
			"Internal Meeting", filters={"series": first.name, "name": ["!=", first.name]}
		)
		self.assertEqual(len(second), 1)
		self.assertEqual(frappe.db.get_value("Internal Meeting", second[0].name, "status"), "Invited")
		self.assertTrue(self.mail)

	def test_only_the_organizer_manages_the_series(self):
		first = make_meeting(self.organizer, [self.member], conference_provider="Zoom")
		frappe.set_user(self.member)
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc("Internal Meeting", first.name).create_repeats("Weekly", count=2)

	def test_update_following_keeps_dates(self):
		first, (second, third) = self.make_series()
		second.title = "Weekly sync v2"
		second.starts_at = get_datetime("2030-03-11 14:00:00")
		second.ends_at = get_datetime("2030-03-11 14:30:00")
		second.set("attendees", [{"user": self.organizer}, {"user": self.other}])
		second.invitation_message = second.build_invitation_message()
		second.save()

		self.assertEqual(second.update_following(), [third.name])
		third.reload()
		self.assertEqual(third.title, "Weekly sync v2")
		self.assertEqual(
			(str(third.starts_at), str(third.ends_at)), ("2030-03-18 14:00:00", "2030-03-18 14:30:00")
		)
		self.assertEqual({row.user for row in third.attendees}, {self.organizer, self.other})
		self.assertIn("2030-03-18 14:00", third.invitation_message)
		first.reload()
		self.assertEqual(first.title, "Weekly sync", "earlier meetings are not changed")
		update_spec = self.zoom.called("update")[-1][2]
		self.assertEqual(str(update_spec.starts_at), "2030-03-18 14:00:00")

	def test_cancel_following_notifies_invited_attendees(self):
		first, (second, third) = self.make_series()
		second.send_invitations()
		second.reload()
		self.mail.clear()

		self.assertEqual(second.cancel_following(), [second.name, third.name])
		statuses = {
			name: frappe.db.get_value("Internal Meeting", name, "status")
			for name in (first.name, second.name, third.name)
		}
		self.assertEqual(statuses, {first.name: "Planned", second.name: "Cancelled", third.name: "Cancelled"})
		self.assertEqual(len(self.zoom.called("delete")), 2)
		# Only the meeting that had been invited emails a cancellation (to colleagues and to the guest).
		self.assertEqual(len(self.mail), 2)
		self.assertTrue(all(mail["subject"].startswith("Cancelled") for mail in self.mail))
