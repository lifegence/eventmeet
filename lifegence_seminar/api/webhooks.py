"""Inbound webhooks from Stripe and Zoom.

Both endpoints are guest-accessible; authenticity is established solely by the
HMAC signature of the raw request body (see docs/security/guest-endpoint-audit.md).
"""

import hashlib
import hmac
import json
import time

import frappe
from werkzeug.wrappers import Response

from lifegence_seminar.services import conference, registration, stripe_api

ZOOM_SIGNATURE_TOLERANCE_SECONDS = 300


def _json_response(data: dict, status: int = 200) -> Response:
	return Response(json.dumps(data), status=status, content_type="application/json")


@frappe.whitelist(allow_guest=True, methods=["POST"])
def stripe():
	payload = frappe.request.get_data()
	secret = frappe.get_single("Seminar Settings").get_password(
		"stripe_webhook_secret", raise_exception=False
	)
	try:
		stripe_api.verify_webhook(payload, frappe.get_request_header("Stripe-Signature"), secret)
	except stripe_api.StripeSignatureError:
		return _json_response({"error": "invalid signature"}, 400)

	event = json.loads(payload)
	event_type = event.get("type", "")
	if event_type.startswith("checkout.session."):
		registration.handle_checkout_event(event_type, event["data"]["object"])
	return _json_response({"received": True})


def zoom_signature(secret: str, message: str) -> str:
	return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def verify_zoom_request(
	payload: bytes, timestamp: str | None, signature: str | None, secret: str, now=None
) -> bool:
	if not (secret and timestamp and signature):
		return False
	try:
		if abs((now or int(time.time())) - int(timestamp)) > ZOOM_SIGNATURE_TOLERANCE_SECONDS:
			return False
	except ValueError:
		return False
	expected = "v0=" + zoom_signature(secret, f"v0:{timestamp}:{payload.decode()}")
	return hmac.compare_digest(expected, signature)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def zoom():
	payload = frappe.request.get_data()
	secret = frappe.get_single("Conferencing Settings").get_password(
		"zoom_webhook_secret", raise_exception=False
	)
	# Verify every request, including endpoint.url_validation: answering unsigned
	# validation requests would turn this endpoint into an HMAC signing oracle.
	if not verify_zoom_request(
		payload,
		frappe.get_request_header("x-zm-request-timestamp"),
		frappe.get_request_header("x-zm-signature"),
		secret,
	):
		return _json_response({"error": "invalid signature"}, 401)

	body = json.loads(payload)
	event = body.get("event")
	data = body.get("payload") or {}

	if event == "endpoint.url_validation":
		plain_token = data.get("plainToken", "")
		return _json_response(
			{"plainToken": plain_token, "encryptedToken": zoom_signature(secret, plain_token)}
		)

	obj = data.get("object") or {}
	external_id = str(obj.get("id") or obj.get("meeting_id") or "")
	if event in ("meeting.ended", "webinar.ended") and external_id:
		conference.mark_ended(external_id)
	elif event == "meeting.summary_completed" and external_id:
		for session in frappe.get_all(
			"Conference Session", filters={"external_id": external_id, "provider": "Zoom"}, pluck="name"
		):
			frappe.enqueue(
				"lifegence_seminar.services.conference.import_summary",
				session_name=session,
				enqueue_after_commit=True,
			)
	return _json_response({"received": True})
