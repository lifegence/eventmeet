"""Minimal Stripe REST client (Checkout Sessions, Refunds, webhook signatures).

Uses the REST API directly so the app does not depend on the Stripe SDK or on
frappe/payments, which differ between Frappe versions.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from decimal import ROUND_HALF_UP, Decimal

import frappe
import requests
from frappe import _
from frappe.utils import cint, flt

API_BASE = "https://api.stripe.com/v1"
TIMEOUT = 30
SIGNATURE_TOLERANCE_SECONDS = 300

# https://docs.stripe.com/currencies#zero-decimal
ZERO_DECIMAL_CURRENCIES = {
	"bif", "clp", "djf", "gnf", "jpy", "kmf", "krw", "mga", "pyg", "rwf", "ugx", "vnd", "vuv", "xaf", "xof", "xpf",
}  # fmt: skip


class StripeError(Exception):
	pass


class StripeSignatureError(StripeError):
	pass


def to_minor_units(amount, currency: str) -> int:
	value = Decimal(str(flt(amount)))
	if currency.lower() not in ZERO_DECIMAL_CURRENCIES:
		value *= 100
	return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def from_minor_units(amount: int, currency: str) -> float:
	if currency.lower() in ZERO_DECIMAL_CURRENCIES:
		return float(amount)
	return float(Decimal(amount) / 100)


def _secret_key() -> str:
	settings = frappe.get_single("Seminar Settings")
	if not settings.stripe_enabled:
		frappe.throw(_("Online payment is not available. Enable Stripe in Seminar Settings."))
	return settings.get_password("stripe_secret_key")


def _request(method: str, path: str, data: dict | None = None, idempotency_key: str | None = None) -> dict:
	headers = {}
	if idempotency_key:
		headers["Idempotency-Key"] = idempotency_key
	response = requests.request(
		method,
		f"{API_BASE}{path}",
		data=data,
		auth=(_secret_key(), ""),
		headers=headers,
		timeout=TIMEOUT,
	)
	if response.status_code >= 400:
		raise StripeError(f"Stripe {method} {path} failed ({response.status_code}): {response.text}")
	return response.json()


def create_checkout_session(
	*,
	registration: str,
	product_name: str,
	amount,
	currency: str,
	customer_email: str,
	success_url: str,
	cancel_url: str,
	expires_in_minutes: int,
	create_invoice: bool,
) -> dict:
	data = {
		"mode": "payment",
		"client_reference_id": registration,
		"customer_email": customer_email,
		"success_url": success_url,
		"cancel_url": cancel_url,
		# Stripe accepts 30 minutes to 24 hours.
		"expires_at": int(time.time()) + max(cint(expires_in_minutes), 30) * 60,
		"line_items[0][quantity]": 1,
		"line_items[0][price_data][currency]": currency.lower(),
		"line_items[0][price_data][unit_amount]": to_minor_units(amount, currency),
		"line_items[0][price_data][product_data][name]": product_name[:250],
		"metadata[registration]": registration,
		"payment_intent_data[metadata][registration]": registration,
		"locale": "auto",
	}
	if create_invoice:
		data["invoice_creation[enabled]"] = "true"
	return _request("POST", "/checkout/sessions", data, idempotency_key=f"checkout-{registration}")


def retrieve_checkout_session(session_id: str) -> dict:
	return _request("GET", f"/checkout/sessions/{session_id}")


def expire_checkout_session(session_id: str) -> dict:
	return _request("POST", f"/checkout/sessions/{session_id}/expire")


def create_refund(*, payment_intent: str, registration: str, amount_minor: int | None = None) -> dict:
	data = {"payment_intent": payment_intent, "metadata[registration]": registration}
	if amount_minor:
		data["amount"] = amount_minor
	return _request("POST", "/refunds", data, idempotency_key=f"refund-{registration}")


def verify_webhook(payload: bytes, signature_header: str, secret: str, now: int | None = None) -> None:
	"""Validate the Stripe-Signature header (https://docs.stripe.com/webhooks#verify-manually)."""
	if not signature_header or not secret:
		raise StripeSignatureError("Missing signature or secret")

	timestamp = None
	signatures = []
	for item in signature_header.split(","):
		key, _sep, value = item.strip().partition("=")
		if key == "t":
			timestamp = value
		elif key == "v1":
			signatures.append(value)
	if not timestamp or not signatures:
		raise StripeSignatureError("Malformed signature header")

	if abs((now or int(time.time())) - int(timestamp)) > SIGNATURE_TOLERANCE_SECONDS:
		raise StripeSignatureError("Timestamp outside tolerance")

	signed_payload = f"{timestamp}.".encode() + payload
	expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
	if not any(hmac.compare_digest(expected, signature) for signature in signatures):
		raise StripeSignatureError("Signature mismatch")
