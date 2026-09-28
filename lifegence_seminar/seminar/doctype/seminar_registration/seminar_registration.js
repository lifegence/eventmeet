// Copyright (c) 2026, Lifegence and contributors
// For license information, please see license.txt

frappe.ui.form.on("Seminar Registration", {
	refresh(frm) {
		if (frm.is_new()) return;
		const call = (action, confirm_message, args = {}) => {
			const run = () =>
				frm
					.call({
						method: "lifegence_seminar.api.staff.registration_action",
						args: { registration_name: frm.doc.name, action, ...args },
						freeze: true,
					})
					.then(() => frm.reload_doc());
			confirm_message ? frappe.confirm(confirm_message, run) : run();
		};

		if (frm.doc.status === "Pending Payment") {
			frm.add_custom_button(__("Confirm Without Online Payment"), () =>
				call("confirm", __("Confirm this registration (e.g. invoice / bank transfer / invited guest)?"))
			);
		}
		if (["Pending Payment", "Confirmed"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Cancel"), () => call("cancel", __("Cancel this registration without refund?")), __("Actions"));
		}
		if (frm.doc.status === "Confirmed" && frm.doc.stripe_payment_intent) {
			frm.add_custom_button(__("Cancel and Refund"), () => call("refund", __("Cancel and refund the full amount via Stripe?")), __("Actions"));
		}
		if (frm.doc.status === "Confirmed") {
			frm.add_custom_button(__("Resend Confirmation"), () => call("resend"), __("Actions"));
		}
	},
});
