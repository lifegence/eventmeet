import hashlib
import hmac
import time
import unittest

from lifegence_seminar.api.webhooks import verify_zoom_request, zoom_signature
from lifegence_seminar.services import stripe_api


def stripe_header(secret: str, payload: bytes, timestamp: int) -> str:
	signature = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256).hexdigest()
	return f"t={timestamp},v1={signature}"


class TestStripeSignature(unittest.TestCase):
	secret = "whsec_test"
	payload = b'{"type":"checkout.session.completed"}'

	def test_valid_signature(self):
		now = int(time.time())
		stripe_api.verify_webhook(
			self.payload, stripe_header(self.secret, self.payload, now), self.secret, now=now
		)

	def test_accepts_any_matching_v1_during_secret_rotation(self):
		now = int(time.time())
		header = stripe_header(self.secret, self.payload, now) + ",v1=deadbeef"
		stripe_api.verify_webhook(self.payload, header, self.secret, now=now)

	def test_tampered_payload(self):
		now = int(time.time())
		with self.assertRaises(stripe_api.StripeSignatureError):
			stripe_api.verify_webhook(
				b'{"type":"x"}', stripe_header(self.secret, self.payload, now), self.secret, now=now
			)

	def test_expired_timestamp(self):
		old = int(time.time()) - 3600
		with self.assertRaises(stripe_api.StripeSignatureError):
			stripe_api.verify_webhook(
				self.payload, stripe_header(self.secret, self.payload, old), self.secret
			)

	def test_missing_secret_or_header(self):
		with self.assertRaises(stripe_api.StripeSignatureError):
			stripe_api.verify_webhook(self.payload, "", self.secret)
		with self.assertRaises(stripe_api.StripeSignatureError):
			stripe_api.verify_webhook(self.payload, "t=1,v1=a", "")


class TestMinorUnits(unittest.TestCase):
	def test_zero_decimal_currency(self):
		self.assertEqual(stripe_api.to_minor_units(5500, "JPY"), 5500)
		self.assertEqual(stripe_api.from_minor_units(5500, "jpy"), 5500)

	def test_two_decimal_currency(self):
		self.assertEqual(stripe_api.to_minor_units(19.99, "USD"), 1999)
		self.assertEqual(stripe_api.to_minor_units(0.105, "USD"), 11)
		self.assertEqual(stripe_api.from_minor_units(1999, "usd"), 19.99)


class TestZoomSignature(unittest.TestCase):
	secret = "zoom_secret"
	payload = b'{"event":"meeting.ended"}'

	def header(self, timestamp: int) -> str:
		return "v0=" + zoom_signature(self.secret, f"v0:{timestamp}:{self.payload.decode()}")

	def test_valid(self):
		now = int(time.time())
		self.assertTrue(verify_zoom_request(self.payload, str(now), self.header(now), self.secret, now=now))

	def test_invalid_signature(self):
		now = int(time.time())
		self.assertFalse(verify_zoom_request(self.payload, str(now), "v0=bad", self.secret, now=now))

	def test_expired(self):
		old = int(time.time()) - 3600
		self.assertFalse(verify_zoom_request(self.payload, str(old), self.header(old), self.secret))

	def test_missing_parts(self):
		self.assertFalse(verify_zoom_request(self.payload, None, "v0=x", self.secret))
		self.assertFalse(verify_zoom_request(self.payload, "1", "v0=x", ""))
		self.assertFalse(verify_zoom_request(self.payload, "not-a-number", "v0=x", self.secret))
