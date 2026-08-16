import frappe
from frappe.model.document import Document
from frappe.utils import getdate


class ArchiveSettings(Document):
	def validate(self):
		for rule in self.get("doc_type_rules") or []:
			if not rule.doctype_name:
				continue
			if not frappe.db.exists("DocType", rule.doctype_name):
				frappe.throw(f"DocType {rule.doctype_name} does not exist.")

		if self.archive_through_year:
			from erpnext_data_archiver.archiver import fiscal

			cutoff = fiscal.cutoff_after_fiscal_year(self.archive_through_year)
			live_start = fiscal.current_fy_start()
			if getdate(cutoff) > getdate(live_start):
				frappe.throw(
					f"Cannot archive through {self.archive_through_year}: "
					"that would include the current fiscal year."
				)
			self.cutoff_date = cutoff

	def on_update(self):
		from erpnext_data_archiver.archiver.engine import sync_all_archive_tables
		from erpnext_data_archiver.archiver.query_patch import clear_metadata_cache

		clear_metadata_cache()
		if self.enabled:
			sync_all_archive_tables()
