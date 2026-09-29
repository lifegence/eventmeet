import datetime
from unittest.mock import MagicMock, patch

import frappe

from eventmeet.conferencing.providers import ConferenceProviderError, ConferenceSpec, SessionRef
from eventmeet.conferencing.providers.zoom import ZoomClient, ZoomProvider, render_summary_html
from eventmeet.tests.utils import SeminarTestCase


def response(status=200, payload=None):
	mock = MagicMock()
	mock.status_code = status
	mock.json.return_value = payload or {}
	mock.content = b"{}" if payload is not None or status == 200 else b""
	mock.text = str(payload)
	return mock


class TestZoomProvider(SeminarTestCase):
	def setUp(self):
		frappe.cache.delete_value("eventmeet:zoom_token:cid")
		self.provider = ZoomProvider(ZoomClient("acc", "cid", "secret"))
		self.spec = ConferenceSpec(
			topic="Kickoff",
			kind="Webinar",
			starts_at=datetime.datetime(2026, 10, 1, 14, 0),
			duration_minutes=90,
			timezone="Asia/Tokyo",
			registration_required=True,
		)

	@patch("eventmeet.conferencing.providers.zoom.requests")
	def test_create_webinar_payload_and_token_cache(self, requests):
		requests.post.return_value = response(payload={"access_token": "tok", "expires_in": 3600})
		requests.request.return_value = response(
			201, {"id": 123, "join_url": "https://zoom.us/w/123", "password": "abc"}
		)

		created = self.provider.create("host@example.com", self.spec)
		self.assertEqual((created.external_id, created.passcode), ("123", "abc"))

		method, url = requests.request.call_args.args
		body = requests.request.call_args.kwargs["json"]
		self.assertEqual(method, "POST")
		self.assertTrue(url.endswith("/users/host%40example.com/webinars"))
		self.assertEqual(body["type"], 5)
		self.assertEqual(body["start_time"], "2026-10-01T14:00:00")
		self.assertEqual(body["settings"]["approval_type"], 0)
		self.assertFalse(body["settings"]["registrants_confirmation_email"])

		self.provider.create("host@example.com", self.spec)
		self.assertEqual(requests.post.call_count, 1, "token must be cached")

	@patch("eventmeet.conferencing.providers.zoom.requests")
	def test_refreshes_token_once_on_401(self, requests):
		requests.post.return_value = response(payload={"access_token": "tok", "expires_in": 3600})
		requests.request.side_effect = [response(401, {}), response(200, {"start_url": "https://s"})]
		self.assertEqual(self.provider.get_host_url(SessionRef("Meeting", "1")), "https://s")
		self.assertEqual(requests.post.call_count, 2)

	@patch("eventmeet.conferencing.providers.zoom.requests")
	def test_error_raises_provider_error(self, requests):
		requests.post.return_value = response(payload={"access_token": "tok", "expires_in": 3600})
		requests.request.return_value = response(400, {"message": "bad"})
		with self.assertRaises(ConferenceProviderError):
			self.provider.update(SessionRef("Meeting", "1"), self.spec)

	@patch("frappe.utils.data.get_system_timezone", return_value="Asia/Tokyo")
	@patch("eventmeet.conferencing.providers.zoom.requests")
	def test_participants_paginate_and_convert_time(self, requests, _tz):
		requests.post.return_value = response(payload={"access_token": "tok", "expires_in": 3600})
		requests.request.side_effect = [
			response(
				200,
				{
					"participants": [
						{
							"name": "A",
							"user_email": "A@Example.com",
							"join_time": "2026-10-01T05:00:00Z",
							"leave_time": "2026-10-01T06:00:00Z",
							"duration": 3600,
						}
					],
					"next_page_token": "p2",
				},
			),
			response(
				200,
				{"participants": [{"name": "B", "user_email": "", "duration": 90}], "next_page_token": ""},
			),
		]
		records = self.provider.list_participants(SessionRef("Webinar", "123"))
		self.assertEqual(len(records), 2)
		self.assertEqual(records[0].email, "a@example.com")
		self.assertEqual(records[0].join_time, datetime.datetime(2026, 10, 1, 14, 0))
		self.assertEqual(records[0].duration_minutes, 60.0)
		self.assertEqual(records[1].duration_minutes, 1.5)
		second_call = requests.request.call_args_list[1]
		self.assertEqual(second_call.kwargs["params"]["next_page_token"], "p2")

	def test_summary_is_escaped(self):
		html = render_summary_html(
			{
				"summary_overview": "<script>x</script>",
				"summary_details": [{"label": "Budget", "summary": "OK"}],
				"next_steps": ["Send deck"],
			}
		)
		self.assertIn("&lt;script&gt;", html)
		self.assertIn("<li>Send deck</li>", html)
		self.assertIsNone(render_summary_html({}))
