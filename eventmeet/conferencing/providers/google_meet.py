"""Google Meet provider (Google Workspace).

Authentication: a service account with domain-wide delegation. Every call
impersonates the meeting organizer, so the meeting is an event in the
organizer's own Google Calendar, Google sends the invitations, and the
organizer is the Meet host. No licensed host pool is needed.

Grant these scopes to the service account's client ID in the Google Admin console
(Security > Access and data control > API controls > Domain-wide delegation):

  https://www.googleapis.com/auth/calendar.events            create/update/cancel meetings
  https://www.googleapis.com/auth/meetings.space.readonly    attendance (conference records)
  https://www.googleapis.com/auth/directory.readonly         map participants to email addresses
  https://www.googleapis.com/auth/drive.readonly             only if "Import Gemini meeting notes" is on
"""

from __future__ import annotations

import datetime
import json
import re
import time
from urllib.parse import quote

import frappe
from frappe.utils import convert_utc_to_system_timezone, get_system_timezone
from frappe.utils.html_utils import sanitize_html

from eventmeet.conferencing.providers.base import (
	ConferenceProvider,
	ConferenceProviderError,
	ConferenceSpec,
	CreatedConference,
	ParticipantRecord,
	SessionRef,
)

CALENDAR_EVENTS = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
MEET_API = "https://meet.googleapis.com/v2"
PEOPLE_API = "https://people.googleapis.com/v1"
DRIVE_API = "https://www.googleapis.com/drive/v3"

SCOPE_CALENDAR = "https://www.googleapis.com/auth/calendar.events"
SCOPE_MEET = "https://www.googleapis.com/auth/meetings.space.readonly"
SCOPE_DIRECTORY = "https://www.googleapis.com/auth/directory.readonly"
SCOPE_DRIVE = "https://www.googleapis.com/auth/drive.readonly"

TIMEOUT = 20
RECORD_WINDOW = datetime.timedelta(hours=2)
EMAIL_CACHE_SECONDS = 24 * 60 * 60

# Credentials refresh themselves; keep them per worker to avoid a token request per call.
_credentials_cache: dict[tuple, object] = {}


def parse_rfc3339(value: str | None) -> datetime.datetime | None:
	"""Parse Google timestamps (e.g. 2026-10-01T05:00:01.123456789Z) into naive system time."""
	if not value:
		return None
	match = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})?$", value)
	if not match:
		return None
	base, fraction, offset = match.groups()
	moment = datetime.datetime.strptime(base, "%Y-%m-%dT%H:%M:%S")
	if fraction:
		moment = moment.replace(microsecond=int(fraction[:6].ljust(6, "0")))
	if offset and offset != "Z":
		sign = 1 if offset[0] == "+" else -1
		hours, minutes = int(offset[1:3]), int(offset[4:6])
		moment -= sign * datetime.timedelta(hours=hours, minutes=minutes)
	return convert_utc_to_system_timezone(moment).replace(tzinfo=None)


def to_rfc3339_utc(value: datetime.datetime) -> str:
	from zoneinfo import ZoneInfo

	local = value.replace(tzinfo=ZoneInfo(get_system_timezone()))
	return local.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")


class GoogleWorkspaceClient:
	def __init__(self, service_account_info: dict):
		self.info = service_account_info

	def _credentials(self, subject: str, scopes: tuple[str, ...]):
		from google.oauth2 import service_account

		key = (self.info.get("client_email"), self.info.get("private_key_id"), subject, scopes)
		credentials = _credentials_cache.get(key)
		if credentials is None:
			credentials = service_account.Credentials.from_service_account_info(
				self.info, scopes=list(scopes), subject=subject
			)
			_credentials_cache[key] = credentials
		return credentials

	def request(
		self,
		subject: str,
		scopes: tuple[str, ...],
		method: str,
		url: str,
		*,
		params=None,
		json_body=None,
		allow_missing: bool = False,
		raw: bool = False,
	):
		from google.auth.exceptions import GoogleAuthError
		from google.auth.transport.requests import AuthorizedSession

		try:
			session = AuthorizedSession(self._credentials(subject, scopes))
			response = session.request(method, url, params=params, json=json_body, timeout=TIMEOUT)
		except GoogleAuthError as e:
			raise ConferenceProviderError(
				f"Google authorization failed for {subject}. Check domain-wide delegation scopes: {e}"
			) from e

		if allow_missing and response.status_code in (404, 410):
			return None
		if response.status_code >= 400:
			raise ConferenceProviderError(
				f"Google API {method} {url} failed ({response.status_code}): {response.text[:500]}"
			)
		if raw:
			return response.text
		return response.json() if response.content else {}


class GoogleMeetProvider(ConferenceProvider):
	name = "Google Meet"
	native_invitations = True

	def __init__(self, client: GoogleWorkspaceClient, import_notes: bool = False):
		self.client = client
		self.import_notes = import_notes

	@classmethod
	def from_settings(cls) -> GoogleMeetProvider:
		settings = frappe.get_single("Conferencing Settings")
		if not settings.google_meet_enabled:
			raise ConferenceProviderError("Google Meet is not enabled in Conferencing Settings")
		raw_key = settings.get_password("google_service_account_key", raise_exception=False)
		try:
			info = json.loads(raw_key or "")
		except ValueError as e:
			raise ConferenceProviderError("The Google service account key is not valid JSON") from e
		if info.get("type") != "service_account":
			raise ConferenceProviderError(
				"The Google key must be a service account key (type: service_account)"
			)
		return cls(GoogleWorkspaceClient(info), import_notes=bool(settings.google_import_meeting_notes))

	# ------------------------------------------------------------------ calendar
	@staticmethod
	def _event_body(spec: ConferenceSpec) -> dict:
		def when(value: datetime.datetime) -> dict:
			return {"dateTime": value.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": spec.timezone}

		return {
			"summary": spec.topic[:1024],
			"description": spec.agenda or "",
			"start": when(spec.starts_at),
			"end": when(spec.ends_at),
			"attendees": [
				{"email": invitee.email, "optional": bool(invitee.optional)} for invitee in spec.attendees
			],
			"guestsCanModify": False,
		}

	@staticmethod
	def _send_updates(notify: bool) -> str:
		return "all" if notify else "none"

	def _event_url(self, event_id: str) -> str:
		return f"{CALENDAR_EVENTS}/{quote(event_id, safe='')}"

	def create(self, host: str, spec: ConferenceSpec) -> CreatedConference:
		body = self._event_body(spec)
		body["conferenceData"] = {
			"createRequest": {
				"requestId": frappe.generate_hash(length=20),
				"conferenceSolutionKey": {"type": "hangoutsMeet"},
			}
		}
		event = self.client.request(
			host,
			(SCOPE_CALENDAR,),
			"POST",
			CALENDAR_EVENTS,
			params={"conferenceDataVersion": 1, "sendUpdates": self._send_updates(spec.notify)},
			json_body=body,
		)
		event = self._wait_for_conference(host, event)
		return CreatedConference(
			external_id=event["id"],
			join_url=event["hangoutLink"],
			meeting_code=(event.get("conferenceData") or {}).get("conferenceId", ""),
		)

	def _wait_for_conference(self, host: str, event: dict, attempts: int = 3) -> dict:
		"""The Meet link is usually created synchronously, but the API allows a pending state."""
		for _attempt in range(attempts):
			if event.get("hangoutLink"):
				return event
			time.sleep(1)
			event = self.client.request(
				host,
				(SCOPE_CALENDAR,),
				"GET",
				self._event_url(event["id"]),
				params={"conferenceDataVersion": 1},
			)
		if event.get("hangoutLink"):
			return event
		raise ConferenceProviderError("Google Calendar did not create a Meet link for the event")

	def update(self, ref: SessionRef, spec: ConferenceSpec) -> None:
		self.client.request(
			ref.host,
			(SCOPE_CALENDAR,),
			"PATCH",
			self._event_url(ref.external_id),
			params={"conferenceDataVersion": 1, "sendUpdates": self._send_updates(spec.notify)},
			json_body=self._event_body(spec),
		)

	def delete(self, ref: SessionRef, notify: bool = False) -> None:
		self.client.request(
			ref.host,
			(SCOPE_CALENDAR,),
			"DELETE",
			self._event_url(ref.external_id),
			params={"sendUpdates": self._send_updates(notify)},
			allow_missing=True,
		)

	def get_host_url(self, ref: SessionRef) -> str:
		# The organizer joins with their own Google account and is the host.
		event = self.client.request(ref.host, (SCOPE_CALENDAR,), "GET", self._event_url(ref.external_id))
		return event.get("hangoutLink", "")

	# ---------------------------------------------------------------- meet api
	def _paged(self, subject: str, scopes: tuple[str, ...], url: str, key: str, params=None) -> list[dict]:
		items: list[dict] = []
		params = dict(params or {})
		while True:
			data = self.client.request(subject, scopes, "GET", url, params=params) or {}
			items.extend(data.get(key) or [])
			token = data.get("nextPageToken")
			if not token:
				return items
			params["pageToken"] = token

	def _conference_records(self, ref: SessionRef) -> list[dict]:
		if not ref.meeting_code:
			raise ConferenceProviderError("The session has no Google Meet meeting code")
		conditions = [f'space.meeting_code = "{ref.meeting_code}"']
		if ref.starts_at:
			conditions.append(f'start_time >= "{to_rfc3339_utc(ref.starts_at - RECORD_WINDOW)}"')
		if ref.ends_at:
			conditions.append(f'start_time <= "{to_rfc3339_utc(ref.ends_at + RECORD_WINDOW)}"')
		records = self._paged(
			ref.host,
			(SCOPE_MEET,),
			f"{MEET_API}/conferenceRecords",
			"conferenceRecords",
			{"filter": " AND ".join(conditions), "pageSize": 25},
		)
		if not records:
			raise ConferenceProviderError("No Google Meet conference record yet")
		return records

	def _email_for(self, user_resource: str, subject: str) -> str:
		"""Map users/{id} to an email address via the People API (domain directory)."""
		user_id = user_resource.split("/", 1)[-1]
		cache_key = f"eventmeet:gmeet_email:{user_id}"
		cached = frappe.cache.get_value(cache_key, expires=True)
		if cached is not None:
			return cached
		email = ""
		try:
			person = self.client.request(
				subject,
				(SCOPE_DIRECTORY,),
				"GET",
				f"{PEOPLE_API}/people/{quote(user_id, safe='')}",
				params={"personFields": "emailAddresses"},
				allow_missing=True,
			)
			addresses = (person or {}).get("emailAddresses") or []
			primary = next((a for a in addresses if (a.get("metadata") or {}).get("primary")), None)
			email = ((primary or (addresses[0] if addresses else {})).get("value") or "").strip().lower()
		except ConferenceProviderError:
			frappe.logger("eventmeet").warning(f"Could not resolve email for {user_resource}")
		frappe.cache.set_value(cache_key, email, expires_in_sec=EMAIL_CACHE_SECONDS)
		return email

	def list_participants(self, ref: SessionRef) -> list[ParticipantRecord]:
		result: list[ParticipantRecord] = []
		for record in self._conference_records(ref):
			participants = self._paged(
				ref.host,
				(SCOPE_MEET,),
				f"{MEET_API}/{record['name']}/participants",
				"participants",
				{"pageSize": 250},
			)
			for participant in participants:
				sessions = self._paged(
					ref.host,
					(SCOPE_MEET,),
					f"{MEET_API}/{participant['name']}/participantSessions",
					"participantSessions",
					{"pageSize": 250},
				)
				seconds = 0.0
				for session in sessions:
					start, end = (
						parse_rfc3339(session.get("startTime")),
						parse_rfc3339(session.get("endTime")),
					)
					if start and end:
						seconds += max((end - start).total_seconds(), 0)

				identity = (
					participant.get("signedinUser")
					or participant.get("anonymousUser")
					or participant.get("phoneUser")
					or {}
				)
				email = ""
				if participant.get("signedinUser", {}).get("user"):
					email = self._email_for(participant["signedinUser"]["user"], ref.host)
				result.append(
					ParticipantRecord(
						name=identity.get("displayName", ""),
						email=email,
						join_time=parse_rfc3339(participant.get("earliestStartTime")),
						leave_time=parse_rfc3339(participant.get("latestEndTime")),
						duration_minutes=round(seconds / 60, 1),
					)
				)
		return result

	def get_summary_html(self, ref: SessionRef) -> str | None:
		"""Import "Take notes for me" (Gemini) documents when enabled."""
		if not self.import_notes:
			return None
		parts: list[str] = []
		for record in self._conference_records(ref):
			notes = self._paged(
				ref.host, (SCOPE_MEET,), f"{MEET_API}/{record['name']}/smartNotes", "smartNotes"
			)
			for note in notes:
				document = (note.get("docsDestination") or {}).get("document")
				if note.get("state") != "FILE_GENERATED" or not document:
					continue
				exported = self.client.request(
					ref.host,
					(SCOPE_DRIVE,),
					"GET",
					f"{DRIVE_API}/files/{quote(document, safe='')}/export",
					params={"mimeType": "text/html"},
					raw=True,
				)
				body = re.search(r"<body[^>]*>(.*)</body>", exported or "", re.S | re.I)
				parts.append(sanitize_html((body.group(1) if body else exported) or ""))
		return "".join(parts) or None
