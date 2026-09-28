# Guest endpoint audit — lifegence_seminar

Every `allow_guest=True` endpoint and every guest-reachable page, with its authorization,
input validation and rate limiting. Update this table whenever a guest path changes.

| Endpoint / page | Method | Authorization | Input validation | Rate limit |
|---|---|---|---|---|
| `lifegence_seminar.api.public.register` | POST | Seminar must be published, `Open`, before `registration_closes_at`; capacity checked under a row lock on the Seminar | name/email/company/phone trimmed and length-limited, email validated, ticket must be an enabled ticket of the seminar, honeypot field `website` | 10 / 10 min / IP |
| `lifegence_seminar.api.public.submit_feedback` | POST | 40-char random `access_token` of a **Confirmed** registration; seminar must have started; one feedback per registration | rating 1–5, comments ≤ 5000 chars | 10 / 10 min / IP |
| `lifegence_seminar.api.webhooks.stripe` | POST | `Stripe-Signature` HMAC-SHA256 over the raw body with the webhook signing secret, 300 s timestamp tolerance | Only `checkout.session.*` events are processed; checkout id must match the registration; `amount_total` and currency must match the registration | Stripe-side |
| `lifegence_seminar.api.webhooks.zoom` | POST | `x-zm-signature` HMAC-SHA256 (`v0:{timestamp}:{body}`) with the Zoom secret token, 300 s tolerance. **Also enforced for `endpoint.url_validation`**, otherwise the endpoint would be an HMAC signing oracle | Only `meeting.ended`, `webinar.ended`, `meeting.summary_completed` change state (status flag / enqueue summary import) | Zoom-side |
| `/seminars`, `/seminars/<name>` | GET | Published seminars only (WebsiteGenerator `published`) | — | — |
| `/seminar-registration?token=` | GET | `access_token` (≥ 20 chars, exact match) | Output escaped with `| e` | — |
| `/seminar-feedback?token=` | GET | `access_token` of a Confirmed registration | Only the stored token is echoed into the page script | — |
| `/seminar-checkin?token=` | GET | Login required; roles Seminar Staff / Seminar Manager / System Manager | Only the stored token is echoed into the page script | — |

`ignore_permissions=True` writes reachable from these paths are limited to
`Seminar Registration`, `Seminar Feedback` and `Conference Session`, and happen only after the
checks listed above.

Note: Frappe's Jinja environment does not auto-escape. All guest-supplied values in web pages
and emails are rendered with `| e`.
