# Zoom Seminar Setup and Operation Guide

EventMeet ─ Running online / hybrid seminars with Zoom

Applies to: EventMeet 0.1.0 or later (Frappe v15 / v16). Audience: Zoom account administrators, Frappe system administrators, seminar organizers (Seminar Manager).

[日本語](../ja/zoom-seminar-guide.md)

> [!IMPORTANT]
> This guide was written from the EventMeet source code and **has not yet been tested against a real Zoom account**.
>
> Before using it for a real seminar, go through "6. First-run verification" with a test seminar and fill in the result column. Zoom screen names and layouts change with Zoom updates. If what you see differs from this guide, please let us know in a GitHub issue.

## 1. Overview

### 1.1 Purpose

This guide describes the Zoom and Frappe settings needed to hold EventMeet seminars on Zoom, and how to run a seminar from creation to checking attendance afterwards. For Google Meet in internal meetings, see the [Google Workspace Setup Guide](google-meet-setup.md).

### 1.2 How the integration works

- Frappe calls the Zoom API through a Zoom **Server-to-Server OAuth app**. Authentication is per Zoom account, so individual hosts do not need to authorize anything.
- When you set a seminar's status to "Open" and save, a **registration-based meeting** (or webinar) is created in Zoom automatically. The host is picked automatically from the licenses registered as "Zoom Host Account", choosing one that is free at that time.
- When a registration is confirmed, the registrant is added as a Zoom registrant and receives a **personal join URL** in the confirmation email (Zoom itself sends no email). The reminder email before the start contains the same URL.
- Changing the seminar's title or date/time updates Zoom too; setting the status to "Cancelled" deletes the Zoom meeting.
- After the seminar, participants and their viewing time are imported from Zoom's participant report and recorded per registration as "Attended Online" and "Online Minutes".
- A Zoom webhook notifies the end of the meeting (recommended; without it, attendance is still imported based on the scheduled end time).

### 1.3 Zoom plan requirements

| Item | Details |
|---|---|
| Host licenses | Zoom users with a paid license (Pro or higher). One license can run only one meeting at a time, so **the number of licenses you need is the peak number of concurrent sessions** (not the number of employees) |
| Webinars | To use the webinar format, assign the Zoom Webinars add-on (with an attendee limit) to the host user. Not needed for regular registration-based meetings |
| Participant reports | Attendance and viewing time are imported from Zoom reports (Pro or higher) |
| Permission to create apps | A Zoom administrator must give the user who creates the Server-to-Server OAuth app the permission to do so through their role |

### 1.4 Where each step is done, and by whom

| Steps | Where | Who |
|---|---|---|
| 3.1–3.5 Create the app, scopes, webhook, activation | **Zoom App Marketplace** (`https://marketplace.zoom.us/`) | Zoom account owner or administrator |
| 3.6 Host users and licenses | **Zoom web portal** (`https://zoom.us/`), "User Management" | Zoom account owner or administrator |
| 4 EventMeet settings | **Frappe** (`https://<site>/app/...`) | System Manager or Seminar Manager |
| 5 Running seminars | **Frappe** | Seminar Manager (Seminar Staff may also do on-site check-in) |

### 1.5 Frappe roles

| Role | Can do |
|---|---|
| System Manager / Seminar Manager | Change Conferencing Settings, Zoom Host Accounts and Seminar Settings; create and change seminars; manage registrations; Start as Host; Sync Attendance |
| Seminar Staff | View seminars; view and update registrations; QR check-in on the day |
| Other users | No access to seminar screens |

## 2. Prerequisites checklist

| Check | Item |
|---|---|
| □ | You can use the Zoom account owner or an administrator account |
| □ | You have users with a paid license to act as hosts (e.g. seminar-host01@example.com), plus the Webinars add-on if you will use webinars |
| □ | You can sign in to Frappe as System Manager or Seminar Manager |
| □ | The Frappe site is reachable from the internet over HTTPS (needed for the webhook; e.g. `https://erp.example.com`) |
| □ | To sell paid tickets, Stripe is set up (see the [README](../../README.md#stripe); out of scope for this guide) |

## 3. Zoom setup

### 3.1 Create a Server-to-Server OAuth app

> **Screen:** Zoom App Marketplace (`https://marketplace.zoom.us/`)

1. Sign in to the Zoom App Marketplace as a Zoom account administrator.
2. At the top right, choose "Develop" > "Build App".
3. Choose "Server to Server OAuth App" as the app type and create it. Name it e.g. `EventMeet`.
4. On the "Information" page, enter the company name and the developer contact (name and email address).

> [!NOTE]
> If "Server to Server OAuth App" cannot be selected, a Zoom administrator must grant the view/edit permission for Server-to-Server OAuth apps to the user's role in "User Management" > "Roles".

### 3.2 Note the credentials

> **Screen:** Zoom App Marketplace (the app's "App Credentials" page)

1. Note the **Account ID**, **Client ID** and **Client Secret** shown on the "App Credentials" page. You enter them in Frappe in 4.1.

> [!WARNING]
> The Client Secret is a secret that can operate the meetings of your Zoom account. Do not paste it into email or chat, and delete your notes once it is registered in Frappe.

### 3.3 Add scopes

> **Screen:** Zoom App Marketplace (the app's "Scopes" page)

1. On the "Scopes" page, click "Add Scopes".
2. Search for and add all scopes in the table below (a list for copying is in Appendix A).

| Scope | Purpose |
|---|---|
| `meeting:write:meeting:admin` | Create meetings |
| `meeting:update:meeting:admin` | Update meetings |
| `meeting:delete:meeting:admin` | Delete meetings |
| `meeting:read:meeting:admin` | Read meetings (host start URL) |
| `meeting:write:registrant:admin` | Add registrants |
| `meeting:update:registrant_status:admin` | Cancel registrants |
| `webinar:write:webinar:admin` | Create webinars |
| `webinar:update:webinar:admin` | Update webinars |
| `webinar:delete:webinar:admin` | Delete webinars |
| `webinar:read:webinar:admin` | Read webinars (host start URL) |
| `webinar:write:registrant:admin` | Add webinar registrants |
| `webinar:update:registrant_status:admin` | Cancel webinar registrants |
| `report:read:list_meeting_participants:admin` | Meeting participant report (attendance, viewing time) |
| `report:read:list_webinar_participants:admin` | Webinar participant report (attendance, viewing time) |
| `meeting:read:summary:admin` | AI Companion meeting summary (for internal meetings; optional) |

> [!NOTE]
> Even if you do not use webinars, we recommend adding the `webinar:` scopes now, so that you can start using webinars later without changing the app.

### 3.4 Set up the webhook (Event Subscription)

> **Screen:** Zoom App Marketplace (the app's "Feature" page)

This lets Zoom notify EventMeet when a seminar ends. Part way through, you must first complete the Frappe setting in 4.1.

1. On the "Feature" page, turn on "Event Subscriptions" and click "Add Event Subscription".
2. Enter a subscription name (e.g. `EventMeet`).
3. Note the **Secret Token** shown on the page.
4. **Now go to 4.1, enter the Secret Token in Frappe's "Webhook Secret Token" field and save.** (Frappe uses the Secret Token to answer Zoom's validation request, so the next step fails unless it is registered first.)
5. Back in Zoom, enter the following URL as the "Event notification endpoint URL" and click "Validate". Replace `<site>` with the host name of your Frappe site (e.g. `erp.example.com`).

```
https://<site>/api/method/eventmeet.api.webhooks.zoom
```

6. In "Add Events", add the following events and save.

| Event (example display name) | Event name | Purpose | Required |
|---|---|---|---|
| End Meeting | `meeting.ended` | End of meeting-format seminars and internal meetings | Recommended |
| End Webinar | `webinar.ended` | End of webinar-format seminars | If you use webinars |
| Meeting summary completed | `meeting.summary_completed` | Import of AI Companion summaries for internal meetings (not used for seminars) | Optional |

> [!NOTE]
> Event display names may change in Zoom's screens. Type part of the event name (e.g. `meeting.ended`) in the search box to find it.

### 3.5 Activate the app

> **Screen:** Zoom App Marketplace (the app's "Activation" page)

1. On the "Activation" page, click "Activate your app". If the app is not activated, authentication from Frappe fails.

### 3.6 Prepare host users and licenses

> **Screen:** Zoom web portal (`https://zoom.us/`) > "User Management" > "Users"

1. Check that the users who will host seminars have a paid license (Pro or higher). Dedicated seminar users (e.g. seminar-host01@example.com) are not affected when staff change roles.
2. To use webinars, assign the Webinars add-on to the user and note its attendee limit (e.g. 500).
3. Note each user's meeting participant limit (e.g. 100 for Pro, or the size of a Large Meetings add-on). You enter it in 4.2.
4. To save automatic recordings to the cloud, check that the license includes cloud recording.

## 4. Frappe (EventMeet) setup

### 4.1 Conferencing Settings

> **Screen:** Frappe (`https://<site>/app/conferencing-settings`)

1. Sign in to Frappe as System Manager (or Seminar Manager) and open "Conferencing Settings".
2. Set the following fields in the "Zoom" section and save.

| Section | Field (as shown) | Value |
|---|---|---|
| Zoom | Enable Zoom | On |
| Zoom | Account ID | Account ID noted in 3.2 |
| Zoom | Client ID | Client ID noted in 3.2 |
| Zoom | Client Secret | Client Secret noted in 3.2 |
| Zoom | Webhook Secret Token | Secret Token noted in 3.4 |
| Zoom | Auto Recording | none / local (host's computer) / cloud (Zoom cloud) |
| Zoom | Waiting Room for Internal Meetings | Setting for internal meetings held on Zoom (does not affect seminars) |
| Zoom Host Allocation | Buffer Between Sessions (Minutes) | Time kept free before and after each session of the same host (e.g. 15) |
| Zoom Host Allocation | Attendance Sync Delay (Minutes) | Time from the scheduled end until attendance import starts (default 15) |

> [!NOTE]
> Seminars always use Zoom. "Internal Meeting Provider" in the "Defaults" section applies to internal meetings only and can stay as Google Meet.
>
> The Client Secret and Webhook Secret Token are stored encrypted and shown as "*****".

### 4.2 Register Zoom Host Accounts

> **Screen:** Frappe (`https://<site>/app/zoom-host-account/new`)

Register the host users prepared in 3.6, one record each. You need as many as the number of seminars you want to run at the same time.

| Field (as shown) | Value |
|---|---|
| Label | A recognizable name (e.g. Seminar host 1) |
| Zoom User | The host user's email address (or Zoom user ID) |
| Enabled | On |
| License | Pro / Business / Business Plus / Enterprise |
| Meeting Capacity | The user's meeting participant limit (e.g. 100) |
| Webinar Capacity | The attendee limit of the Webinars add-on; 0 if none |
| Use for Seminars | On |
| Use for Internal Meetings | Off if you do not use Zoom for internal meetings |

> [!NOTE]
> Among hosts whose capacity is at least the seminar's "Capacity", the one with the smallest capacity is chosen (so that large licenses stay free for large seminars). A capacity of 0 (unlimited) counts as 1 attendee.

### 4.3 Seminar Settings (emails)

> **Screen:** Frappe (`https://<site>/app/seminar-settings`)

| Field (as shown) | Value |
|---|---|
| Send Reminder Hours Before | When to send the reminder email with the personal join URL (e.g. 24) |
| Send Feedback Request After Seminar | On if you use the survey |

The Frappe site sends emails to registrants, so an outgoing email account must be set up in Frappe.

## 5. Running a seminar

### 5.1 Create the seminar (draft)

> **Screen:** Frappe ("Seminar" > "New")

1. On the "Overview" tab, enter Title, Format, Organizer, Starts At, Ends At, Registration Closes At (defaults to the start time if empty) and Capacity. Choose "Online" for online only, or "Hybrid" for both a venue and online (Hybrid requires a venue).
2. Enter the Summary, Description, Banner Image and Program. The Summary is shown in the seminar list.
3. On the "Tickets" tab, add at least one ticket type (price 0 for free).
4. On the "Online" tab, choose the "Conference Kind". "Meeting" is a registration-based Zoom meeting; "Webinar" is a Zoom webinar (requires the Webinars add-on).
5. On the "Website" tab, turn on "Published".
6. Leave the status as "Draft" and save. Nothing is created in Zoom yet.

> [!WARNING]
> If the capacity exceeds every host's limit, 5.2 fails with "No Zoom Host Available". Reduce the capacity or register a host with a larger limit.

### 5.2 Open registration

1. Set the status to "**Open**" and save.
2. On save, the Zoom meeting (or webinar) is created automatically and "Conference Session" and "Join URL (Generic)" are filled in on the "Online" tab.
3. Click "View on Website" and check that the seminar appears on the public page (`/seminars`).

> [!WARNING]
> "Join URL (Generic)" is the Zoom registration page URL. Registrants automatically receive a personal join URL, so do not hand out the generic URL (people who register directly in Zoom through it are not recorded as EventMeet registrations and their attendance is not imported).

### 5.3 Registrations and personal join URLs

- Registrants sign up on the public page (`https://<site>/seminars`). Free tickets are confirmed immediately; paid tickets are confirmed after the Stripe payment completes.
- On confirmation, the registrant is registered in Zoom and receives the personal join URL in the confirmation email. It is also stored in the registration's "Personal Join URL" field.
- If registering with Zoom fails temporarily, it is retried automatically every 10 minutes, and the confirmation email is sent once it succeeds.
- Open the list of registrations with the "Registrations" button on the seminar.

### 5.4 On the day

- A few minutes before the start, a Seminar Manager clicks "Zoom" > "**Start as Host**" on the seminar to open Zoom as the assigned host. This link has full host rights; do not share it.
- Participants join from the personal join URL they received by email.
- For hybrid seminars, Seminar Staff check people in at the venue by scanning QR codes at `/seminar-checkin`.

### 5.5 Checking attendance afterwards

1. Attendance import starts automatically 15 minutes ("Attendance Sync Delay") after the scheduled end time. It runs every 10 minutes and retries up to 12 times if Zoom's report is not ready yet.
2. To check right away, click "Zoom" > "**Sync Attendance**" on the seminar.
3. Check "Attended Online" and "Online Minutes" on each registration. Matching is by email address, so it covers people who joined through their personal join URL.
4. When done, set the seminar's status to "Completed" and save.

> [!NOTE]
> Importing Zoom AI Companion meeting summaries is a feature of internal meetings only. It is not done for seminars.

### 5.6 Changes and cancellation

- **Changing date/time or title**: saving the seminar updates Zoom automatically. Personal join URLs stay the same. Notify registrants of the change separately if needed (Zoom does not notify them).
- **Cancellation**: set the status to "Cancelled" and save to delete the Zoom meeting. Contact registrants and refund paid tickets per registration.
- **Cancelling a registration**: cancelling a registration also cancels it in Zoom, and the personal join URL stops working.

## 6. First-run verification

Because this guide is untested, the first time go through the following with a test seminar (free ticket, small capacity, unpublish it after the test) and fill in the result column.

| No. | Action | Expected result | Result |
|---|---|---|---|
| 1 | After saving the settings in 4.1, click "Validate" in 3.4 | Validation succeeds in Zoom |  |
| 2 | Create a seminar with Format "Online", Conference Kind "Meeting", one free ticket and Published on, and save with status "Draft" | Saves. Nothing is created in Zoom yet |  |
| 3 | Set the status to "Open" and save | "Conference Session" and "Join URL (Generic)" are filled in. A registration-based meeting exists in the host's Zoom account (check in the Zoom web portal) |  |
| 4 | Register with your own email address at `/seminars` | The registration becomes "Confirmed" and a confirmation email with a personal join URL arrives. You are listed as a registrant of the Zoom meeting |  |
| 5 | Change the seminar's start time and save | The Zoom meeting's time changes too |  |
| 6 | Click "Zoom" > "Start as Host" | Zoom opens as the host |  |
| 7 | Join from another device with the personal join URL, leave after a few minutes and end the meeting | If the webhook is set up, the status of the "Conference Session" in Frappe becomes "Ended" |  |
| 8 | Check 15 minutes or more after the scheduled end time (or click "Sync Attendance" right away) | "Attended Online" is on and "Online Minutes" is filled in on the registration |  |
| 9 | (If you use webinars) Repeat 2–8 with Conference Kind "Webinar" | Same results |  |
| 10 | Set another test seminar to "Open", then to "Cancelled" and save | The Zoom meeting is deleted |  |

> [!NOTE]
> After verification, unpublish the test seminars and set their status to "Cancelled".

## 7. Troubleshooting

Error details are in Frappe's "Error Log" list.

| Symptom / error | Likely cause | What to do |
|---|---|---|
| "Zoom authentication failed (400/401)" | Wrong Account ID / Client ID / Client Secret, or the app is not activated | Re-enter the values from 3.2. Activate the app in 3.5 |
| "Zoom API … failed (400)" or (403) mentioning missing scopes | Required scopes have not been added | Add all scopes in 3.3. The app may need to be re-activated after adding scopes |
| "Zoom is not enabled in Conferencing Settings" | Zoom is disabled in Conferencing Settings | Turn on "Enable Zoom" in 4.1 |
| "No enabled Zoom host account can host a Meeting for {N} attendees." | No host used for seminars has a capacity of at least the seminar's capacity | Reduce the capacity, or add/fix hosts in 4.2 (for webinars, check "Webinar Capacity") |
| "All Zoom host accounts are busy between … and …" | All hosts are in use in that time slot (including the buffer before and after) | Add a host or change the time |
| "The online session is not ready yet. Please try again later." on the registration page | Creating the Zoom meeting failed when the status was set to "Open" | Check the Error Log, fix the cause and save the seminar again |
| The confirmation email has no personal join URL | Registering with Zoom failed temporarily | Wait for the automatic retry every 10 minutes. If it continues, check the Error Log |
| Zoom's "Validate" fails | The Secret Token is not saved in Frappe or is wrong, or the site cannot be reached from the internet | Save the Webhook Secret Token in 4.1, then click again. Check that the URL opens over HTTPS |
| Attendance is not imported | Zoom's report is not ready yet, the participant joined via the generic URL or a different email address, or the report scopes are missing | Click "Sync Attendance" later. Ask participants to join via their personal join URL. Check the `report:` scopes in 3.3 |

## 8. Security and operations

- **Secrets**: store the Client Secret and Secret Token only in Frappe and delete your notes. If you suspect a leak, regenerate them in the Zoom App Marketplace and update the Frappe settings.
- **Start as Host link**: it has full host rights; do not share it with anyone other than Seminar Managers.
- **License review**: the number of licenses you need is the peak number of concurrent sessions. Review the number of host accounts against your schedule.
- **Recordings**: if you use cloud recording, set the retention period and sharing in Zoom.
- **Participants' personal data**: use registration and attendance records only for running seminars.

## Appendix A　Scopes (for copying)

```
meeting:write:meeting:admin
meeting:update:meeting:admin
meeting:delete:meeting:admin
meeting:read:meeting:admin
meeting:write:registrant:admin
meeting:update:registrant_status:admin
webinar:write:webinar:admin
webinar:update:webinar:admin
webinar:delete:webinar:admin
webinar:read:webinar:admin
webinar:write:registrant:admin
webinar:update:registrant_status:admin
report:read:list_meeting_participants:admin
report:read:list_webinar_participants:admin
meeting:read:summary:admin
```

## Appendix B　References

| Document | URL |
|---|---|
| Server-to-Server OAuth apps (Zoom Developer) | https://developers.zoom.us/docs/internal-apps/s2s-oauth/ |
| Using webhooks and validating the endpoint (Zoom Developer) | https://developers.zoom.us/docs/api/webhooks/ |
| EventMeet README (Zoom / Stripe setup overview) | [README.md](../../README.md) |
