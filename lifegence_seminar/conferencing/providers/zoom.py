"""Zoom provider (Server-to-Server OAuth app).

Required scopes (granular):
  meeting:write:meeting:admin, meeting:update:meeting:admin, meeting:delete:meeting:admin,
  meeting:read:meeting:admin, meeting:write:registrant:admin, meeting:update:registrant_status:admin,
  webinar:write:webinar:admin, webinar:update:webinar:admin, webinar:delete:webinar:admin,
  webinar:read:webinar:admin, webinar:write:registrant:admin, webinar:update:registrant_status:admin,
  report:read:list_meeting_participants:admin, report:read:list_webinar_participants:admin,
  meeting:read:summary:admin
"""

from __future__ import annotations

import datetime
import html
from urllib.parse import quote

import frappe
import requests
from frappe.utils import convert_utc_to_system_timezone

from lifegence_seminar.conferencing.providers.base import (
	ConferenceProvider,
	ConferenceProviderError,
	ConferenceSpec,
	CreatedConference,
	ParticipantRecord,
	Registrant,
	SessionRef,
)

API_BASE = "https://api.zoom.us/v2"
TOKEN_URL = "https://zoom.us/oauth/token"
TIMEOUT = 20


class ZoomClient:
	def __init__(self, account_id: str, client_id: str, client_secret: str):
		self.account_id = account_id
		self.client_id = client_id
		self.client_secret = client_secret

	@property
	def _token_cache_key(self) -> str:
		return f"lifegence_seminar:zoom_token:{self.client_id}"

	def _get_token(self, force_refresh: bool = False) -> str:
		if not force_refresh:
			# expires=True: never pin a cache miss in frappe.local (v15 would, forcing re-auth per call).
			token = frappe.cache.get_value(self._token_cache_key, expires=True)
			if token:
				return token

		response = requests.post(
			TOKEN_URL,
			params={"grant_type": "account_credentials", "account_id": self.account_id},
			auth=(self.client_id, self.client_secret),
			timeout=TIMEOUT,
		)
		if response.status_code != 200:
			raise ConferenceProviderError(
				f"Zoom authentication failed ({response.status_code}): {response.text}"
			)

		data = response.json()
		token = data["access_token"]
		expires_in = int(data.get("expires_in", 3600))
		frappe.cache.set_value(self._token_cache_key, token, expires_in_sec=max(expires_in - 120, 60))
		return token

	def request(self, method: str, path: str, *, params=None, json=None, allow_404: bool = False):
		for attempt in range(2):
			response = requests.request(
				method,
				f"{API_BASE}{path}",
				params=params,
				json=json,
				headers={"Authorization": f"Bearer {self._get_token(force_refresh=attempt > 0)}"},
				timeout=TIMEOUT,
			)
			if response.status_code == 401 and attempt == 0:
				continue
			break

		if response.status_code == 404 and allow_404:
			return None
		if response.status_code >= 400:
			raise ConferenceProviderError(
				f"Zoom API {method} {path} failed ({response.status_code}): {response.text}"
			)
		if response.status_code == 204 or not response.content:
			return {}
		return response.json()


def _collection(kind: str) -> str:
	if kind == "Webinar":
		return "webinars"
	if kind == "Meeting":
		return "meetings"
	raise ConferenceProviderError(f"Unknown conference kind: {kind}")


def _parse_zoom_time(value: str | None) -> datetime.datetime | None:
	"""Zoom returns UTC timestamps such as 2026-09-28T03:00:00Z."""
	if not value:
		return None
	utc = datetime.datetime.strptime(value.replace("Z", ""), "%Y-%m-%dT%H:%M:%S")
	return convert_utc_to_system_timezone(utc).replace(tzinfo=None)


class ZoomProvider(ConferenceProvider):
	name = "Zoom"
	uses_host_pool = True
	supports_registration = True
	supports_webinar = True

	def __init__(self, client: ZoomClient):
		self.client = client

	@classmethod
	def from_settings(cls) -> ZoomProvider:
		settings = frappe.get_single("Conferencing Settings")
		if not settings.zoom_enabled:
			raise ConferenceProviderError("Zoom is not enabled in Conferencing Settings")
		return cls(
			ZoomClient(
				settings.zoom_account_id,
				settings.zoom_client_id,
				settings.get_password("zoom_client_secret"),
			)
		)

	def _payload(self, spec: ConferenceSpec) -> dict:
		settings = {
			"approval_type": 0 if spec.registration_required else 2,
			"auto_recording": spec.auto_recording or "none",
			# Confirmation and join links are sent by this app, not by Zoom.
			"registrants_email_notification": False,
			"registrants_confirmation_email": False,
		}
		if spec.registration_required:
			settings["registration_type"] = 1
		if spec.kind == "Meeting":
			settings["waiting_room"] = bool(spec.waiting_room)
			settings["join_before_host"] = not spec.waiting_room

		return {
			"topic": spec.topic[:200],
			"type": 5 if spec.kind == "Webinar" else 2,
			"start_time": spec.starts_at.strftime("%Y-%m-%dT%H:%M:%S"),
			"duration": int(spec.duration_minutes),
			"timezone": spec.timezone,
			"agenda": (spec.agenda or "")[:2000],
			"settings": settings,
		}

	def create(self, host: str, spec: ConferenceSpec) -> CreatedConference:
		data = self.client.request(
			"POST", f"/users/{quote(host, safe='')}/{_collection(spec.kind)}", json=self._payload(spec)
		)
		return CreatedConference(
			external_id=str(data["id"]), join_url=data.get("join_url", ""), passcode=data.get("password", "")
		)

	def update(self, ref: SessionRef, spec: ConferenceSpec) -> None:
		payload = self._payload(spec)
		payload.pop("type")
		self.client.request("PATCH", f"/{_collection(ref.kind)}/{ref.external_id}", json=payload)

	def delete(self, ref: SessionRef, notify: bool = False) -> None:
		self.client.request("DELETE", f"/{_collection(ref.kind)}/{ref.external_id}", allow_404=True)

	def add_registrant(self, ref: SessionRef, email: str, first_name: str, last_name: str = "") -> Registrant:
		data = self.client.request(
			"POST",
			f"/{_collection(ref.kind)}/{ref.external_id}/registrants",
			json={"email": email, "first_name": first_name[:64], "last_name": (last_name or "")[:64]},
		)
		return Registrant(
			registrant_id=str(data.get("registrant_id") or data.get("id")), join_url=data.get("join_url", "")
		)

	def cancel_registrant(self, ref: SessionRef, registrant_id: str, email: str) -> None:
		self.client.request(
			"PUT",
			f"/{_collection(ref.kind)}/{ref.external_id}/registrants/status",
			json={"action": "cancel", "registrants": [{"id": registrant_id, "email": email}]},
			allow_404=True,
		)

	def get_host_url(self, ref: SessionRef) -> str:
		data = self.client.request("GET", f"/{_collection(ref.kind)}/{ref.external_id}")
		return data.get("start_url", "")

	def list_participants(self, ref: SessionRef) -> list[ParticipantRecord]:
		records: list[ParticipantRecord] = []
		next_page_token = ""
		while True:
			params = {"page_size": 300}
			if next_page_token:
				params["next_page_token"] = next_page_token
			data = self.client.request(
				"GET", f"/report/{_collection(ref.kind)}/{ref.external_id}/participants", params=params
			)
			for row in data.get("participants", []):
				records.append(
					ParticipantRecord(
						name=row.get("name", ""),
						email=(row.get("user_email") or "").strip().lower(),
						join_time=_parse_zoom_time(row.get("join_time")),
						leave_time=_parse_zoom_time(row.get("leave_time")),
						duration_minutes=round(int(row.get("duration") or 0) / 60, 1),
					)
				)
			next_page_token = data.get("next_page_token") or ""
			if not next_page_token:
				return records

	def get_summary_html(self, ref: SessionRef) -> str | None:
		if ref.kind != "Meeting":
			return None
		data = self.client.request("GET", f"/meetings/{ref.external_id}/meeting_summary", allow_404=True)
		if not data:
			return None
		return render_summary_html(data)


def render_summary_html(data: dict) -> str | None:
	parts: list[str] = []
	if data.get("summary_overview"):
		parts.append(f"<p>{html.escape(data['summary_overview'])}</p>")
	for detail in data.get("summary_details") or []:
		label = html.escape(detail.get("label") or "")
		text = html.escape(detail.get("summary") or "")
		parts.append(f"<h4>{label}</h4><p>{text}</p>" if label else f"<p>{text}</p>")
	next_steps = data.get("next_steps") or []
	if next_steps:
		items = "".join(f"<li>{html.escape(step)}</li>" for step in next_steps)
		parts.append(f"<h4>Next Steps</h4><ul>{items}</ul>")
	return "".join(parts) or None
