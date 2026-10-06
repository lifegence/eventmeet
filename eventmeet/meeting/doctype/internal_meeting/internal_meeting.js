// Copyright (c) 2026, Lifegence and contributors
// For license information, please see license.txt

frappe.ui.form.on("Internal Meeting", {
	insert_invitation_template(frm) {
		const insert = () =>
			frm.call({ doc: frm.doc, method: "build_invitation_message" }).then((r) => {
				frm.set_value("invitation_message", r.message);
				frappe.show_alert({ message: __("Overview and agenda inserted"), indicator: "green" });
			});
		const current = (frm.doc.invitation_message || "").replace(/<[^>]*>/g, "").trim();
		if (current) {
			frappe.confirm(__("Replace the current invitation message?"), insert);
		} else {
			insert();
		}
	},

	refresh(frm) {
		const can_manage = can_manage_meeting(frm);
		if (!is_manager()) frm.set_df_property("organizer", "read_only", 1);
		if (!can_manage) lock_organizer_fields(frm);
		if (frm.is_new()) return;
		render_ai_summary_status(frm);

		const tool = frm.doc.conference_provider || "Zoom";
		const is_google = tool === "Google Meet";
		if (frm.doc.join_url && frm.doc.status !== "Cancelled") {
			frm.add_custom_button(__("Join"), () => window.open(frm.doc.join_url, "_blank"), __(tool));
			if (!is_google) eventmeet.add_host_button(frm, __(tool));
		}
		if (frm.doc.conference_session) {
			eventmeet.add_session_buttons(frm, __(tool));
		}
		if (!can_manage) return;

		// Google Calendar notifies cancellations itself once invitations were sent.
		if (frm.doc.status === "Cancelled" && (is_google || !frm.doc.invitations_sent)) return;
		const cancelled = frm.doc.status === "Cancelled";
		const label = cancelled
			? __("Send Cancellation")
			: frm.doc.invitations_sent
			? __("Resend Invitation")
			: __("Send Invitation");
		const confirm_message = is_google
			? __("Google Calendar will email the invitation to all attendees. Continue?")
			: __("Email all attendees with a calendar invitation?");
		frm.add_custom_button(label, () => {
			if (!ensure_saved(frm)) return;
			frappe.confirm(confirm_message, () => send(frm));
		});

		frm.add_custom_button(
			cancelled ? __("Send Cancellation to Selected") : __("Send to Selected Attendees"),
			() => {
				if (!ensure_saved(frm)) return;
				const rows = ["attendees", "external_attendees"].flatMap((field) =>
					frm.fields_dict[field].grid.get_selected_children()
				);
				const emails = [...new Set(rows.map((row) => row.email).filter(Boolean))];
				if (!emails.length) {
					frappe.msgprint(__("Tick the attendees to send to in the attendee tables first."));
					return;
				}
				const note = is_google
					? "<br><br>" +
					  __(
							"Google Calendar cannot notify only some guests, so they receive an email from this system (without a calendar attachment)."
					  )
					: "";
				frappe.confirm(
					__("Send to the following {0} people?", [emails.length]) +
						"<br>" +
						emails.map((email) => frappe.utils.escape_html(email)).join("<br>") +
						note,
					() => send(frm, emails)
				);
			}
		);
	},
});

// Attendees who do not organize the meeting edit only these (the server discards anything else).
const ATTENDEE_EDITABLE_FIELDS = ["minutes", "actions"];
// Kept in sync with the summary window of eventmeet.services.conference.
const SUMMARY_WINDOW_HOURS = 48;

function is_manager() {
	return frappe.session.user === "Administrator" || frappe.user.has_role(["System Manager", "Seminar Manager"]);
}

function can_manage_meeting(frm) {
	if (frm.is_new() || is_manager()) return true;
	return [frm.doc.organizer, frm.doc.owner].includes(frappe.session.user);
}

function lock_organizer_fields(frm) {
	frm.meta.fields.forEach((df) => {
		if (ATTENDEE_EDITABLE_FIELDS.includes(df.fieldname)) return;
		if (df.fieldtype === "Button") {
			frm.set_df_property(df.fieldname, "hidden", 1);
		} else if (
			frappe.model.table_fields.includes(df.fieldtype) ||
			!frappe.model.no_value_type.includes(df.fieldtype)
		) {
			frm.set_df_property(df.fieldname, "read_only", 1);
		}
	});
}

function render_ai_summary_status(frm) {
	const field = frm.get_field("ai_summary_status");
	if (!field || frm.doc.ai_summary) return;

	let message;
	if (!frm.doc.online) {
		message = __("AI summaries are imported only for online meetings.");
	} else if (
		moment(frm.doc.ends_at).add(SUMMARY_WINDOW_HOURS, "hours").isBefore(moment(frappe.datetime.now_datetime()))
	) {
		message = __("No AI summary was imported for this meeting.");
	} else {
		const how =
			frm.doc.conference_provider === "Google Meet"
				? __('Start Gemini "Take notes for me" during the meeting.')
				: __("Zoom AI Companion meeting summary must be enabled.");
		message =
			__("The AI summary is imported automatically about 15 to 25 minutes after the scheduled end time.") +
			" " +
			how;
	}
	field.$wrapper.html(
		`<div class="form-group">
			<div class="clearfix"><label class="control-label">${__("AI Summary / Meeting Notes")}</label></div>
			<div class="text-muted small">${frappe.utils.escape_html(message)}</div>
		</div>`
	);
}

function ensure_saved(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint(__("Save the meeting before sending the invitation."));
		return false;
	}
	return true;
}

function send(frm, recipients) {
	return frm
		.call({
			doc: frm.doc,
			method: "send_invitations",
			args: recipients ? { recipients } : {},
			freeze: true,
		})
		.then(() => {
			frappe.show_alert({ message: __("Invitation sent"), indicator: "green" });
			frm.reload_doc();
		});
}
