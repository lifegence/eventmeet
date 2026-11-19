# Changelog

## 0.5.1 - 2026-11-19

### Fixed

- Seminar Feedback can no longer be created from the desk (the "+" in the seminar's Connections and "New" in
  the list opened an empty form, as every field is read-only). Answers come only from the survey link.

## 0.5.0 - 2026-11-19

### Added

- Registration form questions per seminar ("Tickets" > "Registration Form"): require the company, hide the
  phone number, ask for the department and job title, questions for the speakers, individual consultation
  and topics of interest (several can be chosen). Seminar Settings can require consent to the handling of
  personal information (with a privacy policy link; the time of consent is stored) and offer an optional,
  unchecked opt-in to further information. The seminar's Registrations tab shows consultation requests.
- Join information on a set day: with "Send Join Information At", registrants confirmed before that time
  receive the join URL and "How to Join" in a separate email at that time, and later registrants with their
  confirmation. Each registration records whether it was sent, so nobody receives it twice.
- Own join URL: an online seminar can send the same URL to every registrant instead of creating a Zoom
  session.
- Contact email (Seminar Settings or per seminar), shown on the registration page and in the emails.
- After registering, the page tells the registrant that the confirmation email was sent, when the join link
  follows and to check the spam folder.

- Operational notes on the seminar form: the "Online" tab explains how participants' microphone and camera are
  set (Zoom host settings, webinar, own join URL) and what saving sends to Zoom; "Attendee Emails" lists when
  each email is sent, computed from the seminar's times.

- Email design: the attendee emails share a card layout with a logo, an accent colour (buttons) and a footer,
  set in Seminar Settings > Email Design. Dates read "2026年11月30日（月）12:00〜13:00" in Japanese.
  "Emails > Preview" on a seminar shows each email for a sample registrant without sending anything.

### Changed

- Reminders are checked every 10 minutes instead of hourly, and a seminar can set its own "Send Reminder
  Hours Before" (e.g. 2 hours). The reminder includes "How to Join".
- Confirmation, join information, reminder and cancellation emails are sent from a background job right
  after the commit instead of waiting for the scheduler's email queue flush (up to a few minutes).
- Registrants confirmed after the reminder time do not receive the reminder minutes after the confirmation
  (online seminars: when the confirmation gave the join link).
- When a delayed Zoom registration succeeds, the registrant receives the join information instead of a second
  confirmation email.

## 0.4.0 - 2026-11-18

### Added

- Registration sources: the seminar pages remember the UTM parameters of the landing URL
  (`utm_source`, `utm_medium`, `utm_campaign`, `utm_term`, `utm_content`) and the referring page for the
  browser tab, and the registration form sends them. They are stored in a new "Source" section of the
  Seminar Registration (filterable by source and campaign) and shown in the seminar's Registrations tab.
  Malformed values are dropped instead of blocking the registration.

## 0.3.0 - 2026-10-13

### Added

- Recurring internal meetings: "Series > Repeat..." creates the later meetings of a series (weekdays,
  weekly, every 2 weeks, monthly on the same date or the same weekday; up to 52 meetings, by count or
  end date), optionally sending the invitations. Each occurrence is a separate meeting with its own
  online meeting, invitations, attendance and minutes. "Update Following Meetings" copies a meeting's
  details to the later ones (each keeps its date) and "Cancel This and Following Meetings" cancels
  them, notifying invited attendees.
- Google Meet: Conferencing Settings > "Calendar for Organizers outside Workspace". Google Meet meetings
  of organizers outside the Workspace domains are created in that account's calendar and the organizer
  is invited as a guest; previously they were rejected. Changing the account affects only new meetings.
- Seminar form: registrations at a glance. Connections (registrations and feedback with counts),
  indicators (confirmed / capacity, pending payment, checked in) and a Registrations tab listing the
  attendees.
- Internal meetings: the invitation is emailed to the organizer too, including for Google Meet (Google
  does not email organizers about their own events). Conferencing Settings > "Send Invitations to the
  Organizer" (on by default) turns it off.

### Changed

- Google Meet invitations sent by email (the organizer copy, "Send to Selected Attendees") now carry an
  .ics with the Google event's UID, so calendars merge it with the Google Calendar event instead of
  adding a second one.

## 0.2.1 - 2026-10-06

- Website design: a **Custom** design. Custom CSS now applies only when Custom is selected (on top of
  the Standard design), so switching to another built-in design no longer mixes it with your CSS; the
  CSS is kept for when you switch back. Sites with the Standard design and Custom CSS are moved to
  Custom on migrate.
- Sample custom CSS and header / footer HTML in `examples/website-design`, with screenshots in the
  website design guide.

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
