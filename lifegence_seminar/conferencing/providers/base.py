"""Provider-agnostic conferencing interface.

Seminars and internal meetings only talk to this interface (through
``lifegence_seminar.services.conference``), so Zoom can later be replaced by
Google Meet or a self-hosted WebRTC stack without touching the business logic.
"""

from __future__ import annotations

import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass


class ConferenceProviderError(Exception):
	"""Raised when the remote conferencing service rejects a request."""


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


@dataclass
class CreatedConference:
	external_id: str
	join_url: str
	passcode: str = ""


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

	@abstractmethod
	def create(self, host: str, spec: ConferenceSpec) -> CreatedConference: ...

	@abstractmethod
	def update(self, kind: str, external_id: str, spec: ConferenceSpec) -> None: ...

	@abstractmethod
	def delete(self, kind: str, external_id: str) -> None: ...

	@abstractmethod
	def add_registrant(
		self, kind: str, external_id: str, email: str, first_name: str, last_name: str = ""
	) -> Registrant: ...

	@abstractmethod
	def cancel_registrant(self, kind: str, external_id: str, registrant_id: str, email: str) -> None: ...

	@abstractmethod
	def get_host_url(self, kind: str, external_id: str) -> str: ...

	@abstractmethod
	def list_participants(self, kind: str, external_id: str) -> list[ParticipantRecord]: ...

	def get_summary_html(self, kind: str, external_id: str) -> str | None:
		"""Return an AI-generated summary if the provider offers one, else None."""
		return None
