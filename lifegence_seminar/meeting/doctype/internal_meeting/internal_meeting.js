// Copyright (c) 2026, Lifegence and contributors
// For license information, please see license.txt

frappe.ui.form.on("Internal Meeting", {
	refresh(frm) {
		if (frm.is_new()) return;

		if (frm.doc.join_url && frm.doc.status !== "Cancelled") {
			frm.add_custom_button(__("Join"), () => window.open(frm.doc.join_url, "_blank"), __("Zoom"));
			lifegence_seminar.add_host_button(frm, __("Zoom"));
		}
		if (frm.doc.conference_session) {
			lifegence_seminar.add_session_buttons(frm, __("Zoom"));
		}
		frm.add_custom_button(
			frm.doc.status === "Cancelled" ? __("Send Cancellation") : __("Send Invitation"),
			() =>
				frappe.confirm(__("Email all attendees with a calendar invitation?"), () =>
					frm.call({ doc: frm.doc, method: "send_invitations", freeze: true }).then(() => {
						frappe.show_alert({ message: __("Invitation queued"), indicator: "green" });
						frm.reload_doc();
					})
				)
		);
	},
});
