// Copyright (c) 2026, Lifegence and contributors
// For license information, please see license.txt

const HELP_FIELDS = [
	"format",
	"starts_at",
	"conference_kind",
	"use_own_join_url",
	"join_info_send_at",
	"reminder_hours_before",
	"feedback_enabled",
	"feedback_form_url",
];

frappe.ui.form.on("Seminar", {
	onload(frm) {
		frappe.db
			.get_value("Seminar Settings", "Seminar Settings", ["reminder_hours_before", "send_feedback_request"])
			.then(({ message }) => {
				frm.__default_reminder_hours = (message && message.reminder_hours_before) || 0;
				frm.__send_feedback_request = cint(message && message.send_feedback_request);
				render_help(frm);
			});
	},
	refresh(frm) {
		render_help(frm);
		if (frm.is_new()) return;

		frm.add_custom_button(__("Registrations"), () =>
			frappe.set_route("List", "Seminar Registration", { seminar: frm.doc.name })
		);
		if (frm.doc.published && frm.doc.route) {
			frm.add_custom_button(__("View on Website"), () => window.open(`/${frm.doc.route}`, "_blank"));
		}
		if (frm.doc.conference_session && !["Cancelled", "Draft"].includes(frm.doc.status)) {
			eventmeet.add_host_button(frm, __("Zoom"));
			eventmeet.add_session_buttons(frm, __("Zoom"));
		}
		if (frm.doc.format !== "Offline" && !frm.doc.conference_session && frm.doc.status === "Draft") {
			frm.set_intro(__("The Zoom session is created automatically when the status is set to Open."));
		}
		frm.add_custom_button(__("Preview"), () => preview_emails(frm), __("Emails"));
		load_registrations(frm);
	},
	...Object.fromEntries(HELP_FIELDS.map((field) => [field, (frm) => render_help(frm)])),
});

// Operational notes next to the settings they concern, computed from the current values.
function render_help(frm) {
	render_online_help(frm);
	render_attendee_emails_help(frm);
}

function help_box(items) {
	const list = items.map((item) => `<li>${item}</li>`).join("");
	return `<div class="text-muted small" style="margin-bottom: 12px"><ul style="padding-left: 18px; margin: 0">${list}</ul></div>`;
}

function render_online_help(frm) {
	const field = frm.get_field("online_help");
	if (!field) return;
	let items;
	if (frm.doc.use_own_join_url) {
		items = [
			__("No Zoom meeting is created: set up the meeting (microphone, camera, waiting room) in the service you use."),
			__("Attendance is not imported, so the attended/no-show status stays empty."),
		];
	} else if (frm.doc.conference_kind === "Webinar") {
		items = [
			__("In a webinar, attendees cannot use their microphone or camera unless the host allows it."),
			__("Saving the seminar sends its title, time and registration settings to Zoom again; change other settings in Zoom."),
		];
	} else {
		items = [
			__("Participants join with the microphone and camera settings of the Zoom host account (Zoom web portal > Settings: \"Mute all participants when they join a meeting\", \"Participants video: off\")."),
			__("Participants can turn their microphone and camera on themselves. To prevent it, use a webinar, or turn off \"Allow participants to unmute themselves\" in Zoom during the meeting."),
			__("Saving the seminar sends its title, time, waiting room and join-before-host setting to Zoom again; settings changed directly in Zoom for these are overwritten."),
		];
	}
	field.$wrapper.html(help_box(items));
}

function render_attendee_emails_help(frm) {
	const field = frm.get_field("attendee_emails_help");
	if (!field) return;
	const doc = frm.doc;
	const fmt = (value) => (value ? frappe.datetime.str_to_user(value) : "");
	const online = doc.format !== "Offline";
	const items = [];
	if (online && doc.join_info_send_at) {
		items.push(
			__("Confirmation email: right after registering, without the join link (it says the link follows on {0}).", [
				fmt(doc.join_info_send_at),
			])
		);
		items.push(
			__("Join information: on {0} to registrants confirmed by then (within 10 minutes). Later registrants receive the join link with their confirmation.", [
				fmt(doc.join_info_send_at),
			])
		);
	} else if (online) {
		items.push(__("Confirmation email: right after registering, with the join link."));
	} else {
		items.push(__("Confirmation email: right after registering, with the check-in QR code."));
	}
	const hours = cint(doc.reminder_hours_before) || cint(frm.__default_reminder_hours);
	if (hours > 0) {
		const at = doc.starts_at
			? moment(doc.starts_at).subtract(hours, "hours").format("YYYY-MM-DD HH:mm:ss")
			: "";
		items.push(
			__("Reminder: {0} hours before the start{1} to confirmed registrants (within 10 minutes).", [
				hours,
				at ? ` (${fmt(at)})` : "",
			])
		);
	} else {
		items.push(__("Reminder: not sent (0 hours in the Seminar Settings)."));
	}
	if (!doc.feedback_enabled || !frm.__send_feedback_request) {
		items.push(__("Survey request: not sent."));
	} else if (doc.feedback_form_url) {
		items.push(__("Survey request: within an hour after the end, to confirmed registrants, with the link to the external survey form."));
	} else {
		items.push(__("Survey request: within an hour after the end, to confirmed registrants, with the link to the built-in survey."));
	}
	items.push(__("Before announcing the seminar, register with your own address to check the emails."));
	field.$wrapper.html(help_box(items));
}

const STATUS_COLORS = {
	Confirmed: "green",
	"Pending Payment": "orange",
	Cancelled: "gray",
	Expired: "gray",
	Refunded: "gray",
};

function load_registrations(frm) {
	const name = frm.doc.name;
	frm.call("get_registration_overview").then(({ message }) => {
		if (!message || frm.doc.name !== name) return;
		show_indicators(frm, message);
		render_registrations(frm, message);
	});
}

function show_indicators(frm, { capacity, counts, checked_in }) {
	const confirmed = counts["Confirmed"] || 0;
	const pending = counts["Pending Payment"] || 0;
	const full = capacity && confirmed + pending >= capacity;
	frm.dashboard.add_indicator(
		capacity
			? __("Confirmed: {0} / Capacity {1}", [confirmed, capacity])
			: __("Confirmed: {0}", [confirmed]),
		full ? "red" : "green"
	);
	if (pending) frm.dashboard.add_indicator(__("Pending Payment: {0}", [pending]), "orange");
	if (checked_in) frm.dashboard.add_indicator(__("Checked In: {0}", [checked_in]), "blue");
}

function render_registrations(frm, { registrations, truncated }) {
	const $wrapper = frm.get_field("registrations_html").$wrapper;
	const esc = frappe.utils.escape_html;
	const check = (value) => (value ? "✓" : "");
	const source = (r) => [r.utm_source, r.utm_campaign].filter(Boolean).join(" / ");
	const rows = registrations
		.map(
			(r) => `<tr>
				<td><a href="/app/seminar-registration/${encodeURIComponent(r.name)}">${esc(r.attendee_name || r.name)}</a></td>
				<td>${esc(r.email || "")}</td>
				<td>${esc(r.company || "")}</td>
				<td>${esc(r.ticket_type || "")}</td>
				<td>${esc(source(r))}</td>
				<td><span class="indicator-pill ${STATUS_COLORS[r.status] || "gray"}">${esc(__(r.status, null, "Seminar Registration"))}</span></td>
				<td class="text-center">${check(r.checked_in)}</td>
				<td class="text-center">${check(r.attended_online)}</td>
				<td class="text-center">${check(r.consultation_requested)}</td>
			</tr>`
		)
		.join("");
	$wrapper.html(`
		<div class="mb-3">
			<button class="btn btn-xs btn-default" data-action="open-list">${__("Open List")}</button>
			<button class="btn btn-xs btn-default" data-action="add">${__("Add Registration")}</button>
		</div>
		${
			registrations.length
				? `<div class="table-responsive"><table class="table table-bordered table-sm">
					<thead><tr>
						<th>${__("Attendee Name")}</th>
						<th>${__("Email")}</th>
						<th>${__("Company")}</th>
						<th>${__("Ticket Type")}</th>
						<th>${__("Source")}</th>
						<th>${__("Status")}</th>
						<th class="text-center">${__("Checked In")}</th>
						<th class="text-center">${__("Attended Online")}</th>
						<th class="text-center">${__("Consultation")}</th>
					</tr></thead>
					<tbody>${rows}</tbody>
				</table></div>`
				: `<p class="text-muted">${__("No registrations yet.")}</p>`
		}
		${
			truncated
				? `<p class="text-muted small">${__(
						"Showing the first {0} registrations. Open the list to see all.",
						[registrations.length]
				  )}</p>`
				: ""
		}
	`);
	$wrapper.find("[data-action=open-list]").on("click", () =>
		frappe.set_route("List", "Seminar Registration", { seminar: frm.doc.name })
	);
	$wrapper.find("[data-action=add]").on("click", () =>
		frappe.new_doc("Seminar Registration", { seminar: frm.doc.name })
	);
}

const EMAIL_KINDS = [
	["confirmation", __("Confirmation")],
	["join_info", __("Join Information")],
	["reminder", __("Reminder")],
	["cancellation", __("Cancellation")],
	["feedback", __("Survey Request")],
];

// The attendee emails for a sample registrant, rendered by the server exactly as they would be sent now.
function preview_emails(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Email Preview"),
		size: "large",
		fields: [
			{
				fieldname: "kind",
				fieldtype: "Select",
				label: __("Email"),
				options: EMAIL_KINDS.map(([value, label]) => ({ value, label })),
				default: "confirmation",
				change: () => show(dialog.get_value("kind")),
			},
			{ fieldname: "subject", fieldtype: "HTML" },
			{ fieldname: "body", fieldtype: "HTML" },
		],
	});
	const show = (kind) =>
		frm.call("preview_email", { kind }).then(({ message }) => {
			if (!message) return;
			dialog.fields_dict.subject.$wrapper.html(
				`<div class="text-muted small">${__("Subject")}</div><div class="mb-3"><strong>${frappe.utils.escape_html(message.subject)}</strong></div>`
			);
			const iframe = $('<iframe sandbox="" style="width: 100%; height: 640px; border: 1px solid var(--border-color); border-radius: 6px;"></iframe>');
			iframe.attr("srcdoc", message.html);
			dialog.fields_dict.body.$wrapper.empty().append(iframe);
		});
	dialog.show();
	show("confirmation");
}
