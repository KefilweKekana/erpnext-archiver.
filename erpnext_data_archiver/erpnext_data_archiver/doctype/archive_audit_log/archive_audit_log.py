# Copyright (c) 2026, Hiraal and contributors
from frappe.model.document import Document


class ArchiveAuditLog(Document):
	def on_trash(self):
		import frappe

		frappe.throw("Archive Audit Log entries are append-only and cannot be deleted.")
