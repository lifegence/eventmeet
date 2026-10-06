# EventMeet

**Seminar and internal meeting management for [Frappe](https://frappeframework.com/)** (v15 / v16).

- **Seminars** (online, on-site or hybrid): planning, a public registration page, paid tickets with
  Stripe, Zoom meetings or webinars with a personal join link for each registrant, QR check-in,
  reminders, attendance import and a feedback survey.
- **Internal meetings**: agenda, internal and external attendees, invitations, minutes and action
  items synced with ToDo. Run them on Zoom or Google Meet; with Google Meet, the event lives in the
  organizer's Google Calendar and Gemini "Take notes for me" summaries are imported into the minutes.

[日本語の README](README_ja.md)

> EventMeet is an independent open-source project and is not affiliated with Frappe Technologies.
> Zoom, Google Meet and Stripe are trademarks of their respective owners.

## Status

EventMeet 0.1.0 is the first public release. Every integration is covered by automated tests with
mocked APIs; verification against the live services is still in progress:

| Integration | Verified against the live service |
|---|---|
| Google Meet (internal meetings) | Yes: event and Meet link creation, Google Calendar invitations, attendance and Gemini notes import (Frappe 16.33) |
| Zoom (seminars, internal meetings) | Not yet. Follow the first-run checklist in the [Zoom guide](docs/en/zoom-seminar-guide.md#6-first-run-verification) |
| Stripe (paid tickets) | Not yet |

Reports from your own setup are welcome in the issues.

## Features

| Area | What it does |
|---|---|
| Planning | Seminars (format, schedule, capacity, venue), program, speakers, preparation tasks assigned as ToDo |
| Registration | Public pages at `/seminars`, registration form with ticket types and per-ticket capacity, bot trap and rate limit |
| Payment | Stripe Checkout (cards and asynchronous methods such as konbini), Stripe invoices as receipts, refunds, reconciliation when a webhook is missed, manual confirmation (for example payment by invoice) |
| Online | Registration-based Zoom meetings or webinars created, updated and cancelled automatically; personal join link per registrant; "Start as Host" |
| On the day | QR check-in at `/seminar-checkin` (staff only), reminder emails |
| Afterwards | Zoom attendance import (attended, minutes watched), feedback survey at `/seminar-feedback` |
| Internal meetings | Agenda, attendees, **external guests** (no account needed, invited by email or Google Calendar), invitations, minutes, action items (two-way sync with ToDo); visible to the organizer and attendees only |
| Google Meet | Event with a Meet link in the organizer's Google Calendar, invitations / updates / cancellations sent by Google, attendance import, Gemini "Take notes for me" import |
| Zoom licenses | Hosts are allocated from a pool of licensed accounts, so you need as many licenses as concurrent sessions, not one per employee |

Conferencing tools sit behind the provider interface in `eventmeet/conferencing/providers/`, so another
tool (for example a self-hosted LiveKit or Jitsi) can be added the same way.

| | Zoom | Google Meet |
|---|---|---|
| Used for | Seminars (registration-based meetings / webinars), internal meetings | Internal meetings |
| Host | Allocated from the pool of licensed host accounts | The organizer (a Google Workspace user) |
| Invitations | Email with an .ics file, sent by EventMeet | Google Calendar invitation (sent when you press "Send Invitation") |
| Attendance | Zoom report API | Meet REST API (emails resolved with the People API, display names as a fallback) |
| AI summary | Zoom AI Companion meeting summary | Gemini "Take notes for me" document (optional) |

The user interface ships with a Japanese translation.

## Requirements

| | |
|---|---|
| Frappe | v15 or v16 (ERPNext is not required) |
| Python | 3.10 or later |
| Zoom | A paid account with a Server-to-Server OAuth app and licensed host users (for seminars or Zoom meetings) |
| Google Workspace | A service account with domain-wide delegation (for Google Meet) |
| Stripe | An account, only if you sell paid tickets |

## Installation

```bash
bench get-app https://github.com/lifegence/eventmeet
bench --site <site> install-app eventmeet
bench --site <site> migrate
```

Then open **Conferencing Settings** and **Seminar Settings** as a System Manager.

## Setup

### Zoom

The step-by-step guide, including a first-run checklist, is in
[docs/en/zoom-seminar-guide.md](docs/en/zoom-seminar-guide.md). In short:

1. In the Zoom App Marketplace, create a **Server-to-Server OAuth** app and add the scopes listed in the
   guide (also at the top of `eventmeet/conferencing/providers/zoom.py`).
2. Enable Event Subscriptions with the endpoint `https://<site>/api/method/eventmeet.api.webhooks.zoom`
   and the events `meeting.ended`, `webinar.ended` and (optional) `meeting.summary_completed`.
   Save the Secret Token in Frappe before you press "Validate".
3. In **Conferencing Settings**, enter the Account ID, Client ID, Client Secret and Webhook Secret Token.
4. Add each licensed host user as a **Zoom Host Account** (set **Webinar Capacity** if the user has a
   webinar add-on).
5. To import AI summaries of internal meetings, turn on the AI Companion meeting summary in Zoom.

### Google Meet (internal meetings)

The step-by-step guide (which console to use, verification, troubleshooting) is in
[docs/en/google-meet-setup.md](docs/en/google-meet-setup.md). In short:

1. In the Google Cloud console, create a service account and a JSON key, and enable the Google Calendar
   API, the Google Meet REST API and the People API (and the Google Drive API to import Gemini notes).
2. In the Google Admin console, under **Security > Access and data control > API controls > Manage Domain
   Wide Delegation**, authorize the service account's client ID for:
   - `https://www.googleapis.com/auth/calendar.events`
   - `https://www.googleapis.com/auth/meetings.space.readonly`
   - `https://www.googleapis.com/auth/directory.readonly`
   - `https://www.googleapis.com/auth/drive.readonly` (only to import Gemini notes)
3. In **Conferencing Settings**, enable Google Meet and enter the JSON key and your Workspace domains.
   Set **Internal Meeting Provider** to Google Meet to make it the default.
4. Organizers' Frappe email addresses must match their Workspace accounts.

### Stripe

1. In **Seminar Settings**, enter the Secret Key and the Webhook Signing Secret.
2. Add a webhook endpoint `https://<site>/api/method/eventmeet.api.webhooks.stripe` with the events
   `checkout.session.completed`, `checkout.session.expired`,
   `checkout.session.async_payment_succeeded` and `checkout.session.async_payment_failed`.
3. To issue invoices as receipts (for example Japanese qualified invoices), configure your registration
   number and invoice settings in Stripe.

### Roles

| Role | Can |
|---|---|
| System Manager / Seminar Manager | Change Conferencing Settings, Seminar Settings and Zoom Host Accounts; manage seminars and registrations; start a seminar as host |
| Seminar Staff | View seminars, view and update registrations, check people in on the day |
| Every desk user | Create internal meetings they organize |

Internal meetings are visible to the organizer, the attendees and managers only. Attendees who do not
organize a meeting can edit its minutes and action items, but not its schedule, attendees or agenda,
and cannot send invitations. Only a Seminar Manager can change a meeting's organizer.

## Development

```bash
bench --site <site> set-config allow_tests true
bench --site <site> run-tests --app eventmeet
```

Zoom, Google and Stripe are mocked in the tests. See [CONTRIBUTING.md](CONTRIBUTING.md) for linting
and pull requests.

## Security

Please report vulnerabilities privately; see [SECURITY.md](SECURITY.md). Authorization, input
validation and rate limits of every guest-reachable endpoint are documented in
[docs/security/guest-endpoint-audit.md](docs/security/guest-endpoint-audit.md).

## License

[MIT](license.txt) © 2026 Lifegence Corporation
