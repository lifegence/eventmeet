# Changelog

## 0.2.0 - 2026-10-06

### Added

- Website design for the public pages (`/seminars`, seminar pages, registration status, survey):
  - Seminar Settings > Website Design: four built-in designs (Standard, Corporate, Friendly, Minimal),
    Custom CSS with design tokens (CSS variables), sanitized Header HTML and Footer HTML;
  - template overrides from another app through the `eventmeet_website_templates` hook; the pages are
    split into blocks that can be overridden one by one;
  - an example theme app in `examples/eventmeet_theme_example` and a guide in `docs/en` / `docs/ja`.

### Fixed

- A seminar's banner image replaced the site logo in the navbar of its page.

Fixes found while verifying Zoom seminars against a live Zoom Pro account:

- Zoom: registrants are always sent a last name (the name is split on the first space, `-` if there is
  none). Zoom rejected registrants with "The parameter is required: last_name", so no personal join
  link was issued.
- A registration deadline left at its default (the start time) now moves with the start time;
  previously, moving the start later closed registration early.
- Zoom guide: current App Marketplace menus, report timing, and notes from the verification.

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
