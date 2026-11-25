"""How the public seminar page shows the seats left.

Exact shows the number. Threshold says only "Seats available" until the seats left fall to the
threshold, then shows the number, so a seminar with few registrations does not look empty.
Hidden never shows the number. "Sold out" is shown in every mode.

The mode and the threshold are set in Seminar Settings and can be overridden per seminar and per
ticket type (an empty value means "use the level above").
"""

from __future__ import annotations

from frappe import _
from frappe.utils import cint

EXACT = "Exact"
THRESHOLD = "Threshold"
HIDDEN = "Hidden"
MODES = (EXACT, THRESHOLD, HIDDEN)
DEFAULT_THRESHOLD = 10


def resolve(settings, seminar, ticket) -> tuple[str, int]:
	"""The display mode and threshold for a ticket: ticket type, then seminar, then settings."""
	mode = next(
		(
			lvl.get("seat_display")
			for lvl in (ticket, seminar, settings)
			if lvl is not None and lvl.get("seat_display") in MODES
		),
		EXACT,
	)
	threshold = next(
		(
			cint(lvl.get("seat_display_threshold"))
			for lvl in (ticket, seminar, settings)
			if lvl is not None and cint(lvl.get("seat_display_threshold")) > 0
		),
		DEFAULT_THRESHOLD,
	)
	return mode, threshold


def availability(remaining: int | None, mode: str, threshold: int) -> dict:
	"""What the page may show for a ticket with `remaining` seats left (None = no capacity limit).

	`remaining` in the result is the number the page may show, or None when it must not show one.
	"""
	if remaining is None:
		return {"sold_out": False, "remaining": None, "label": None}
	if remaining <= 0:
		return {"sold_out": True, "remaining": 0, "label": _("Sold out")}
	if mode == EXACT or (mode == THRESHOLD and remaining <= threshold):
		label = (
			_("{0} seats left").format(remaining)
			if mode == EXACT
			else _("Only {0} seats left").format(remaining)
		)
		return {"sold_out": False, "remaining": remaining, "label": label}
	return {"sold_out": False, "remaining": None, "label": _("Seats available")}
