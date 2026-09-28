// Shared desk helpers for documents linked to a Conference Session.
frappe.provide("lifegence_seminar");

lifegence_seminar.add_host_button = function (frm, group) {
	frm.add_custom_button(
		__("Start as Host"),
		() =>
			frappe
				.call({
					method: "lifegence_seminar.api.conference.get_host_url",
					args: { session: frm.doc.conference_session },
					freeze: true,
				})
				.then((r) => r.message && window.open(r.message, "_blank")),
		group
	);
};

lifegence_seminar.add_session_buttons = function (frm, group) {
	const run = (method, message) =>
		frappe
			.call({
				method: `lifegence_seminar.api.conference.${method}`,
				args: { session: frm.doc.conference_session },
				freeze: true,
			})
			.then(() => {
				frappe.show_alert({ message, indicator: "green" });
				frm.reload_doc();
			});
	frm.add_custom_button(__("Sync Attendance"), () => run("sync_attendance", __("Attendance updated")), group);
	if (frm.doctype === "Internal Meeting") {
		frm.add_custom_button(__("Import AI Summary"), () => run("import_summary", __("Summary imported")), group);
	}
};
