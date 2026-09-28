import frappe
from frappe import _

from lifegence_seminar.conferencing.providers.base import (
	ConferenceProvider,
	ConferenceProviderError,
	ConferenceSpec,
	CreatedConference,
	Invitee,
	ParticipantRecord,
	Registrant,
	SessionRef,
)

__all__ = [
	"ConferenceProvider",
	"ConferenceProviderError",
	"ConferenceSpec",
	"CreatedConference",
	"Invitee",
	"ParticipantRecord",
	"Registrant",
	"SessionRef",
	"get_provider",
]

PROVIDERS = ("Zoom", "Google Meet")


def get_provider(name: str) -> ConferenceProvider:
	if name == "Zoom":
		from lifegence_seminar.conferencing.providers.zoom import ZoomProvider

		return ZoomProvider.from_settings()
	if name == "Google Meet":
		from lifegence_seminar.conferencing.providers.google_meet import GoogleMeetProvider

		return GoogleMeetProvider.from_settings()

	frappe.throw(_("Unsupported conference provider: {0}").format(name))
