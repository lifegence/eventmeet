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
		if (frm.is_new()) return;

		const tool = frm.doc.conference_provider || "Zoom";
		const is_google = tool === "Google Meet";
		if (frm.doc.join_url && frm.doc.status !== "Cancelled") {
			frm.add_custom_button(__("Join"), () => window.open(frm.doc.join_url, "_blank"), __(tool));
			if (!is_google) eventmeet.add_host_button(frm, __(tool));
		}
		if (frm.doc.conference_session) {
			eventmeet.add_session_buttons(frm, __(tool));
		}

		// Google Calendar notifies cancellations itself once invitations were sent.
		if (frm.doc.status === "Cancelled" && (is_google || !frm.doc.invitations_sent)) return;
		const label =
			frm.doc.status === "Cancelled"
				? __("Send Cancellation")
				: frm.doc.invitations_sent
				? __("Resend Invitation")
				: __("Send Invitation");
		const confirm_message = is_google
			? __("Google Calendar will email the invitation to all attendees. Continue?")
			: __("Email all attendees with a calendar invitation?");
		frm.add_custom_button(label, () =>
			frappe.confirm(confirm_message, () =>
				frm.call({ doc: frm.doc, method: "send_invitations", freeze: true }).then(() => {
					frappe.show_alert({ message: __("Invitation sent"), indicator: "green" });
					frm.reload_doc();
				})
			)
		);
	},
});
