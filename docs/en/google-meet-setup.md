# Google Workspace Setup Guide

EventMeet ─ Google Meet for internal meetings

Applies to: EventMeet 0.1.0 or later (Frappe v15 / v16). Audience: Google Workspace super administrators, Google Cloud administrators, Frappe system administrators.

[日本語](../ja/google-meet-setup.md)

## 1. Overview

### 1.1 Purpose

This guide describes the Google Cloud, Google Workspace and Frappe settings needed to use Google Meet for EventMeet internal meetings. Seminars (external events) use Zoom and are out of scope (see the [Zoom Seminar Setup and Operation Guide](zoom-seminar-guide.md)).

### 1.2 How the integration works

- Frappe uses a service account and calls Google APIs **as the organizer** through domain-wide delegation.
- Saving an internal meeting creates an event with Google Meet in the organizer's Google Calendar (attendees are not notified yet).
- Pressing "Send Invitation" makes Google Calendar send the invitations to the attendees. Later changes of date/time and cancellations are also notified by Google.
- After the meeting, attendees and their attendance time are imported from the Meet conference record. Attendee email addresses are resolved with the People API.
- Optionally, the Google Doc created by Gemini "Take notes for me" is imported into "AI Summary / Meeting Notes". Meet transcripts (the full record of what was said) are not imported.

### 1.3 APIs and permissions (scopes)

| API | Scope | Purpose | Required |
|---|---|---|---|
| Google Calendar API | `calendar.events` | Create, change and cancel events with Meet; send invitations | Required |
| Google Meet REST API | `meetings.space.readonly` | Read conference records, participants, attendance time and meeting notes | Required |
| People API | `directory.readonly` | Resolve participant IDs to email addresses | Required |
| Google Drive API | `drive.readonly` | Import Gemini meeting notes (documents) | Optional |

The full scope values (`https://www.googleapis.com/auth/...`) are listed in Appendix A.

### 1.4 Where each step is done, and by whom

The work is done in three separate places. **The Google Cloud console and the Google Admin console are different sites.** If you mix them up, you will not find the menus you are looking for, or you may be shown offers for paid services.

| Steps | Where (URL) | Who | Permissions needed |
|---|---|---|---|
| 3.1–3.4 Project, APIs, service account, key | **Google Cloud console**<br>`console.cloud.google.com` | Google Cloud administrator | Create projects; manage service accounts and keys |
| 3.4 Organization policy exception (only if needed) | **Google Cloud console** | Google Cloud organization administrator | Organization Policy Administrator |
| 3.5–3.7 Domain-wide delegation, directory, Gemini | **Google Admin console**<br>`admin.google.com` | Google Workspace administrator | Super administrator |
| 3.8 EventMeet settings | **Frappe**<br>`https://<site>/app/conferencing-settings` | Frappe administrator | System Manager or Seminar Manager |

> [!WARNING]
> "Security" (Security Command Center) in the left menu of the Google Cloud console is a paid security service and is not needed for this guide. If you see pricing plans or a trial offer, do not start it.

## 2. Prerequisites checklist

| Check | Item |
|---|---|
| □ | You can use a Google Workspace super administrator account |
| □ | You can sign in to the Google Cloud console with your Workspace organization account |
| □ | The email address of each Frappe user who will organize meetings matches their Workspace account (e.g. taro@example.com) |
| □ | EventMeet (0.1.0 or later) is installed on the Frappe site |
| □ | (To import Gemini notes) Gemini "Take notes for me" is available in your Workspace |

> [!NOTE]
> Domain-wide delegation (3.5) is available in every Google Workspace edition, including Business Starter. No plan upgrade is needed.

## 3. Setup

### 3.1 Create a Google Cloud project

> **Screen:** Google Cloud console (`https://console.cloud.google.com/`)

1. Sign in to the Google Cloud console with your Workspace organization account.
2. In the project picker at the top, choose "New Project".
3. Enter a project name (e.g. eventmeet), select your Workspace organization as "Organization" and "Location", and click "Create".

> [!NOTE]
> You can use an existing project, but a project dedicated to this integration is recommended so that permissions are managed separately.

### 3.2 Enable the APIs

> **Screen:** Google Cloud console

1. With the project from 3.1 selected, open "APIs & Services" > "Library".
2. Search for each of the following APIs and click "Enable".

| API name | Required |
|---|---|
| Google Calendar API | Required |
| Google Meet REST API | Required |
| People API | Required |
| Google Drive API | Optional (to import Gemini notes) |

### 3.3 Create a service account

> **Screen:** Google Cloud console

1. Go to "IAM & Admin" > "Service Accounts" and click "Create service account".
2. Enter a service account name (e.g. `eventmeet-google`) and a description, then click "Create and continue".
3. No role (project access) is needed. Click "Done".
4. Open the new service account from the list and note the "Unique ID" (a number) on the "Details" tab. This is the "Client ID" you enter in 3.5.

> [!NOTE]
> Access to Workspace data is defined by domain-wide delegation in 3.5. No Google Cloud roles are needed.

### 3.4 Create a JSON key

> **Screen:** Google Cloud console

1. On the service account's "Keys" tab, choose "Add key" > "Create new key".
2. Select "JSON" as the key type and click "Create". A JSON file is downloaded.
3. After registering the file in Frappe in 3.8, delete it from your computer. Do not put it in email, chat or shared drives.

> [!WARNING]
> If you see "Service account key creation is disabled":
>
> In Google Cloud organizations created on or after May 3, 2024, the organization policy `iam.disableServiceAccountKeyCreation` (newer name: `iam.managed.disableServiceAccountKeyCreation`) is enforced by default and keys cannot be created.
>
> An Organization Policy Administrator must override the policy (not enforced) for this project only in "IAM & Admin" > "Organization Policies", then start again from step 1.
>
> You may restore the policy after creating the key. Existing keys keep working, but replacing the key later requires the exception again.

### 3.5 Set up domain-wide delegation (super administrator)

> **Screen:** **Google Admin console** (`https://admin.google.com/`). Not the Google Cloud console.

1. In a new browser tab, sign in to the Google Admin console as a **super administrator**. Check that the account shown at the top right is the super administrator (if you are signed in to several accounts, the page may open with a different one).
2. Open the following URL. To get there from the menu, open Menu > "Security" > "Access and data control" > "API controls" and click "Manage Domain Wide Delegation" at the bottom of the page.

```
https://admin.google.com/ac/owl/domainwidedelegation
```

3. Click "Add new".
4. Enter the Unique ID noted in 3.3 as the "Client ID".
5. Paste the following into "OAuth scopes (comma-delimited)" and click "Authorize".

```
https://www.googleapis.com/auth/calendar.events,https://www.googleapis.com/auth/meetings.space.readonly,https://www.googleapis.com/auth/directory.readonly
```

To import Gemini meeting notes, append the following:

```
,https://www.googleapis.com/auth/drive.readonly
```

> [!NOTE]
> The change can take up to 24 hours to take effect (usually much less).
>
> The top of the "API controls" page may show features of higher editions or upgrade offers. They are unrelated to domain-wide delegation and can be ignored.

> [!WARNING]
> Within the delegated scopes, the service account can access the data of every user in the organization. Do not add any scopes other than those listed in this guide.

### 3.6 Check directory contact sharing

> **Screen:** **Google Admin console** (`https://admin.google.com/`)

This setting lets the People API return participants' email addresses when attendance is matched.

1. In the Google Admin console, click "≡" (Menu) at the top left to show the left menu.
2. Click "Directory" to expand it and open "Directory settings". If you cannot find it, type "Contact sharing" in the search box at the top and open the suggested result.
3. Under "Sharing settings", check that "Contact sharing" is on (turn it on if it is off).
4. On the same page, check that "External Directory sharing" allows the domain profiles to be read through the API.

> [!NOTE]
> If there is no "Directory" in the left menu, check that you are not in the Google Cloud console (the URL must be `admin.google.com`) and that you are signed in as a super administrator.
>
> Meeting creation and invitations work even if sharing is off. However, attendance is then matched by display name only, which fails for people with the same name or a different display name.

### 3.7 Import Gemini meeting notes (optional)

With Meet's "Take notes for me", a Google Doc with a summary is created after the meeting. To import it into EventMeet, set up these three places.

| No. | Where | Setting |
|---|---|---|
| 1 | Google Admin console | Check that Gemini note-taking in Google Meet is turned on for the users concerned |
| 2 | Google Cloud console / Google Admin console | Check that the Google Drive API is enabled (3.2) and `drive.readonly` is delegated (3.5) |
| 3 | Frappe (done in 3.8) | Turn on "Import Gemini Meeting Notes" in Conferencing Settings |

In the meeting, the organizer or an attendee starts "Take notes for me" during the meeting. If it is not started, no summary document is created and nothing is imported.

> [!WARNING]
> Meet transcripts (the full text of what was said) are not imported. EventMeet imports only the summary document from "Take notes for me".

### 3.8 Configure Frappe (EventMeet)

> **Screen:** **Frappe** (`https://<site>/app/conferencing-settings`)

1. Sign in to Frappe as System Manager (or Seminar Manager) and open "Conferencing Settings". You can also search for "Conferencing Settings" in the search bar at the top.
2. In the "Google Meet" section, tick "**Enable Google Meet**". The Google fields appear below it once it is ticked (they are hidden until then).
3. Set the following fields and save.

| Section | Field (as shown) | Value |
|---|---|---|
| Google Meet | Enable Google Meet | On |
| Google Meet | Workspace Domains | Your domain (e.g. example.com). Separate several domains with commas |
| Google Meet | Service Account Key (JSON) | Paste the entire content of the JSON file downloaded in 3.4 |
| Google Meet | Import Gemini Meeting Notes | On only if you completed 3.7 |
| Defaults | Internal Meeting Provider | "Google Meet" to make it the default for internal meetings |

4. Once saved, delete the JSON file from your computer.
5. For each user who will organize meetings, check that their Frappe email address matches their Workspace account.

> [!NOTE]
> The key is stored encrypted in Frappe and shown as "*****". To replace the key, paste the new JSON and save.
>
> Changing the default tool does not change existing internal meetings; they keep their original tool.

## 4. Verification

Check the following in order with a test internal meeting ("Internal Meeting" > "New").

| No. | Action | Expected result |
|---|---|---|
| 1 | Create and save a new internal meeting (Online Meeting: on, Conferencing Tool: Google Meet, at least one attendee) | "Join URL" contains a Meet URL. The event is created in the organizer's Google Calendar. Attendees are not notified yet |
| 2 | Click "Send Invitation" | Attendees receive a Google Calendar invitation email and the event appears in their calendars. Status becomes "Invited" |
| 3 | Change the date/time and save | Attendees receive a change notification from Google |
| 4 | Hold the meeting (organizer and attendees join Meet). To check the AI summary too, start "Take notes for me" during the meeting | ─ |
| 5 | Check 15 minutes or more after the **scheduled end time** (import runs automatically every 10 minutes). To check right away, click "Google Meet" > "Sync Attendance" | Attendance and minutes attended are updated in "Attendees" |
| 6 | (Optional) Open the "Meeting Minutes" tab | Before import, the "AI Summary / Meeting Notes" heading and a note on when it will be imported are shown. The summary appears from about 15–25 minutes after the scheduled end time. If the minutes are empty, the summary is also copied into the minutes as a draft |
| 7 | Set the status to "Cancelled" and save | The event is deleted and attendees receive a cancellation notice from Google (if invitations were sent) |

> [!NOTE]
> Import starts from the "Ends At" time entered in the internal meeting (the scheduled end), not from when the meeting actually ended. Even if the meeting ends early, nothing is imported until 15 minutes after the scheduled end time.

## 5. Troubleshooting

Error details are in Frappe's "Error Log" list.

| Symptom / error | Likely cause | What to do |
|---|---|---|
| Pricing plans (e.g. Security Command Center) are shown in the Google Cloud console | "Security" was opened in the Google Cloud console instead of the Google Admin console | Do 3.5 and 3.6 at `admin.google.com` (see 1.4). Do not start a paid plan |
| "Directory" or "Domain-wide delegation" cannot be found in the Admin console | You are in the Google Cloud console, or not a super administrator | Check that the URL is `admin.google.com` and that the account at the top right is a super administrator. Use the direct URL in 3.5 or the search box at the top |
| "Google authorization failed …" on save (e.g. unauthorized_client) | Delegation not set up, wrong Client ID, missing scopes, or not yet in effect | Check the Client ID and scopes in 3.5. If you just set it up, retry later (up to 24 hours) |
| "Google API … failed (403)" saying an API is disabled | The API is not enabled | Enable the API in 3.2 |
| "Organizer … is not a Google Workspace user of …" | The organizer's email domain is not in Workspace Domains | Make the organizer a Workspace user, or check the domain setting in 3.8 |
| "The organizer needs an email address to host a Google Meet meeting." | The organizer's Frappe user has no email address | Set an email address for the user |
| "The JSON is not a service account key." | A different file was pasted, e.g. an OAuth client JSON | Paste the service account key created in 3.4 |
| Attendance is not imported and the Error Log shows "No Google Meet conference record yet" | The meeting has not taken place yet, or the record is still being generated | Normal before the meeting. Retried automatically up to 12 times. If it continues after the meeting, check the `meetings.space.readonly` delegation |
| Some people who joined are not marked as attended | Their email address could not be resolved and the display name does not match | Check contact sharing in 3.6. Align Frappe full names with Google display names |
| Nothing appears in "AI Summary / Meeting Notes" | Too soon after the scheduled end time, "Take notes for me" was not started, the feature is off, or `drive.readonly` is not delegated | Check again 25 minutes or more after the scheduled end time. Check 3.7 (import is retried automatically for 48 hours after the end) |
| Transcripts are not imported | By design (transcripts are not imported) | Use "Take notes for me" (3.7) |
| The service account key cannot be created | Restricted by an organization policy | See the warning in 3.4 |

## 6. Security and operations

- **Keep scopes to a minimum**: the delegated scopes give access to all users' data, so do not add scopes other than those in this guide.
- **Key management**: delete the key file after registering it in Frappe. Replace the key periodically (e.g. once a year or when the person in charge changes) and delete old keys in Google Cloud.
- **Google Cloud permissions**: keep project owners and editors to a minimum and limit who can create keys.
- **Regular review**: review the domain-wide delegation list in the Admin console regularly and remove delegations that are no longer needed.
- **Purpose of attendance data**: Google does not allow the Meet REST API to be used for performance evaluation or tracking. Use attendance records only for running meetings.
- **Leavers and transfers**: events live in the organizer's calendar, so before deleting a Workspace account, change the organizer of their upcoming internal meetings (a Seminar Manager changes the organizer).

## 7. User permissions

Regular users can create their own meetings, send invitations and write minutes, but cannot change settings.

| Action | System Manager / Seminar Manager | Organizer | Other attendees | Other users |
|---|---|---|---|---|
| Change Conferencing Settings and Zoom Host Accounts | ✓ | × | × | × |
| Create internal meetings | ✓ (any organizer) | ✓ (themselves as organizer only) | ─ | ─ |
| View | All | ✓ | ✓ | × (not shown in lists either) |
| Edit date/time, attendees, agenda, etc. | ✓ | ✓ | × (read-only) | × |
| Edit minutes and action items | ✓ | ✓ | ✓ | × |
| Send invitations | ✓ | ✓ | × (buttons hidden) | × |
| Change the organizer | ✓ | × | × | × |

## Appendix A　Scopes (for copying)

Required (3)

```
https://www.googleapis.com/auth/calendar.events
https://www.googleapis.com/auth/meetings.space.readonly
https://www.googleapis.com/auth/directory.readonly
```

Optional (to import Gemini meeting notes)

```
https://www.googleapis.com/auth/drive.readonly
```

## Appendix B　References

| Document | URL |
|---|---|
| Control API access with domain-wide delegation (Google Workspace Help) | https://knowledge.workspace.google.com/admin/apps/control-api-access-with-domain-wide-delegation |
| Create and delete service account keys (Google Cloud) | https://docs.cloud.google.com/iam/docs/keys-create-delete |
| Secure-by-default organizations (Google Cloud) | https://cloud.google.com/resource-manager/docs/secure-by-default-organizations |
| Meet REST API authentication and authorization (Google for Developers) | https://developers.google.com/workspace/meet/api/guides/authenticate-authorize |
| Allow third-party apps to access directory data (Google Workspace Help) | https://support.google.com/a/answer/6343701 |
