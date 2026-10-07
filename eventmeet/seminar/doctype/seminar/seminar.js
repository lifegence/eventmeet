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
		load_registrations(frm);
	},
});

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
	const rows = registrations
		.map(
			(r) => `<tr>
				<td><a href="/app/seminar-registration/${encodeURIComponent(r.name)}">${esc(r.attendee_name || r.name)}</a></td>
				<td>${esc(r.email || "")}</td>
				<td>${esc(r.company || "")}</td>
				<td>${esc(r.ticket_type || "")}</td>
				<td><span class="indicator-pill ${STATUS_COLORS[r.status] || "gray"}">${esc(__(r.status, null, "Seminar Registration"))}</span></td>
				<td class="text-center">${check(r.checked_in)}</td>
				<td class="text-center">${check(r.attended_online)}</td>
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
						<th>${__("Status")}</th>
						<th class="text-center">${__("Checked In")}</th>
						<th class="text-center">${__("Attended Online")}</th>
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
