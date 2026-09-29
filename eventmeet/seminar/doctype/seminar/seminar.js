// Copyright (c) 2026, Lifegence and contributors
// For license information, please see license.txt

frappe.ui.form.on("Seminar", {
	refresh(frm) {
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
	},
});
