import frappe
from frappe import _

from lifegence_seminar.conferencing.providers.base import (
	ConferenceProvider,
	ConferenceProviderError,
	ConferenceSpec,
	CreatedConference,
	ParticipantRecord,
	Registrant,
)

__all__ = [
	"ConferenceProvider",
	"ConferenceProviderError",
	"ConferenceSpec",
	"CreatedConference",
	"ParticipantRecord",
	"Registrant",
	"get_provider",
]


def get_provider(name: str) -> ConferenceProvider:
	if name == "Zoom":
		from lifegence_seminar.conferencing.providers.zoom import ZoomProvider

		return ZoomProvider.from_settings()

	frappe.throw(_("Unsupported conference provider: {0}").format(name))
