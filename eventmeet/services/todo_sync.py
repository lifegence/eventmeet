"""Two-way sync between assigned child rows (tasks / action items) and ToDo."""

from __future__ import annotations

import frappe
from frappe.utils import strip_html

# parent doctype -> (child table field, child doctype, description field)
TRACKED = {
	"Seminar": ("tasks", "Seminar Task", "task"),
	"Internal Meeting": ("actions", "Internal Meeting Action", "description"),
}


def sync_todos(doc) -> None:
	table_field, _child_doctype, description_field = TRACKED[doc.doctype]
	rows = doc.get(table_field) or []

	previous = doc.get_doc_before_save()
	previous_todos = {row.todo for row in (previous.get(table_field) if previous else []) if row.todo}

	for row in rows:
		description = strip_html(row.get(description_field) or "")[:1000]
		todo_exists = bool(row.todo and frappe.db.exists("ToDo", row.todo))

		if row.assigned_to and row.status == "Open":
			if todo_exists:
				todo = frappe.get_doc("ToDo", row.todo)
				changes = {
					"allocated_to": row.assigned_to,
					"description": description,
					"date": row.due_date,
					"status": "Open",
				}
				if any(todo.get(key) != value for key, value in changes.items()):
					todo.update(changes)
					todo.save(ignore_permissions=True)
			else:
				todo = frappe.get_doc(
					{
						"doctype": "ToDo",
						"allocated_to": row.assigned_to,
						"description": description,
						"reference_type": doc.doctype,
						"reference_name": doc.name,
						"date": row.due_date,
						"assigned_by": frappe.session.user,
					}
				).insert(ignore_permissions=True)
				row.db_set("todo", todo.name, update_modified=False)
		elif todo_exists:
			_close_todo(row.todo, "Closed" if row.status == "Closed" else "Cancelled")
			if not row.assigned_to:
				row.db_set("todo", None, update_modified=False)

	current_todos = {row.todo for row in rows if row.todo}
	for todo_name in previous_todos - current_todos:
		if frappe.db.exists("ToDo", todo_name):
			_close_todo(todo_name, "Cancelled")


def _close_todo(todo_name: str, status: str) -> None:
	todo = frappe.get_doc("ToDo", todo_name)
	if todo.status == "Open":
		todo.flags.from_eventmeet = True
		todo.status = status
		todo.save(ignore_permissions=True)


def on_todo_update(todo, method=None) -> None:
	"""Mirror ToDo close/reopen back to the originating row."""
	if todo.flags.from_eventmeet or todo.reference_type not in TRACKED:
		return
	_table_field, child_doctype, _description_field = TRACKED[todo.reference_type]
	row = frappe.db.get_value(
		child_doctype, {"todo": todo.name, "parent": todo.reference_name}, ["name", "status"], as_dict=True
	)
	if not row:
		return
	status = "Closed" if todo.status == "Closed" else "Open" if todo.status == "Open" else None
	if status and row.status != status:
		frappe.db.set_value(child_doctype, row.name, "status", status, update_modified=False)
