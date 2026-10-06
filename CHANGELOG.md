# Changelog

## 0.1.0 - 2026-10-06

First public release.

- Seminars (online, on-site, hybrid): program, speakers, venues, preparation tasks synced with ToDo,
  ticket types with per-ticket capacity, public pages at `/seminars`, registration with a bot trap and
  rate limit.
- Stripe Checkout for paid tickets, including asynchronous methods, Stripe invoices as receipts,
  refunds, reconciliation of missed webhooks and manual confirmation.
- Zoom: registration-based meetings and webinars created, updated and cancelled with the seminar; a
  personal join link per registrant; hosts allocated from a pool of licensed accounts; attendance
  import; AI Companion summaries for internal meetings.
- QR check-in, reminder emails and a feedback survey.
- Internal meetings: agenda, internal attendees and external guests, invitations (to everyone or to
  ticked attendees), minutes and action items synced with ToDo. Only the organizer (or a manager) can
  change the schedule, attendees and agenda or send invitations; other attendees edit the minutes
  and action items.
- Google Meet for internal meetings: event in the organizer's Google Calendar through domain-wide
  delegation, Google Calendar invitations, attendance import via the Meet REST API, and Gemini
  "Take notes for me" import.
- Japanese translation.
- Setup guides in English and Japanese (`docs/en`, `docs/ja`).
