"""Provider-agnostic conferencing interface.

Seminars and internal meetings only talk to this interface (through
``eventmeet.services.conference``), so providers (Zoom, Google Meet, a
self-hosted WebRTC stack, ...) can be added without touching the business logic.
"""

from __future__ import annotations

import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class ConferenceProviderError(Exception):
	"""Raised when the remote conferencing service rejects a request."""


@dataclass
class Invitee:
	email: str
	optional: bool = False


@dataclass
class ConferenceSpec:
	topic: str
	kind: str  # "Meeting" | "Webinar"
	starts_at: datetime.datetime  # naive, system time zone
	duration_minutes: int
	timezone: str
	registration_required: bool = False
	agenda: str = ""
	waiting_room: bool = False
	auto_recording: str = "none"
	# Used by providers with native invitations (e.g. Google Calendar).
	attendees: list[Invitee] = field(default_factory=list)
	notify: bool = False
	# Rich invitation text (HTML); providers that show a description use it instead of `agenda`.
	description_html: str = ""

	@property
	def ends_at(self) -> datetime.datetime:
		return self.starts_at + datetime.timedelta(minutes=self.duration_minutes)


@dataclass
class SessionRef:
	"""Identifies an existing session on the provider side."""

	kind: str
	external_id: str
	host: str = ""  # provider-side identity that owns the session (Zoom user / Google organizer)
	meeting_code: str = ""
	starts_at: datetime.datetime | None = None  # naive, system time zone
	ends_at: datetime.datetime | None = None


@dataclass
class CreatedConference:
	external_id: str
	join_url: str
	passcode: str = ""
	meeting_code: str = ""
	ical_uid: str = ""


@dataclass
class Registrant:
	registrant_id: str
	join_url: str


@dataclass
class ParticipantRecord:
	name: str
	email: str
	join_time: datetime.datetime | None  # naive, system time zone
	leave_time: datetime.datetime | None
	duration_minutes: float


class ConferenceProvider(ABC):
	name: str = ""
	# Sessions are owned by a pooled licensed host (Zoom) instead of the organizer.
	uses_host_pool: bool = False
	# Provider sends calendar invitations/updates itself (Google Calendar).
	native_invitations: bool = False
	# Provider issues personal join links for registrants (Zoom registration).
	supports_registration: bool = False
	supports_webinar: bool = False

	@abstractmethod
	def create(self, host: str, spec: ConferenceSpec) -> CreatedConference: ...

	@abstractmethod
	def update(self, ref: SessionRef, spec: ConferenceSpec) -> None: ...

	@abstractmethod
	def delete(self, ref: SessionRef, notify: bool = False) -> None: ...

	def add_registrant(self, ref: SessionRef, email: str, first_name: str, last_name: str = "") -> Registrant:
		raise ConferenceProviderError(f"{self.name} does not support registrants")

	def cancel_registrant(self, ref: SessionRef, registrant_id: str, email: str) -> None:
		raise ConferenceProviderError(f"{self.name} does not support registrants")

	@abstractmethod
	def get_host_url(self, ref: SessionRef) -> str: ...

	@abstractmethod
	def list_participants(self, ref: SessionRef) -> list[ParticipantRecord]: ...

	def get_summary_html(self, ref: SessionRef) -> str | None:
		"""Return an AI-generated summary/notes if the provider offers one, else None."""
		return None
