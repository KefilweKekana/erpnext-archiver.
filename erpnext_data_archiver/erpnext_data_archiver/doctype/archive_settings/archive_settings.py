import frappe
from frappe.model.document import Document
from frappe.utils import cint, getdate


class ArchiveSettings(Document):
	def validate(self):
		for rule in self.get("doc_type_rules") or []:
			if not rule.doctype_name:
				continue
			if not frappe.db.exists("DocType", rule.doctype_name):
				frappe.throw(f"DocType {rule.doctype_name} does not exist.")

		if cint(self.monthly_in_current_year) and self.archive_through_month:
			from frappe.utils import add_days

			from erpnext_data_archiver.archiver import fiscal

			cutoff = fiscal.cutoff_after_month(self.archive_through_month)
			cap = fiscal.first_of_current_month()
			if getdate(cutoff) > getdate(cap):
				frappe.throw("Cannot archive the current month. Pick the last completed month.")
			self.cutoff_date = cutoff
			fy = fiscal.fiscal_year_for_date(add_days(getdate(cutoff), -1))
			if fy:
				self.archive_through_year = fy
		elif self.archive_through_year:
			from erpnext_data_archiver.archiver import fiscal

			cutoff = fiscal.cutoff_after_fiscal_year(self.archive_through_year)
			monthly = cint(self.monthly_in_current_year)
			cap = fiscal.max_allowed_cutoff(monthly=monthly)
			if getdate(cutoff) > getdate(cap):
				frappe.throw(
					f"Cannot archive through {self.archive_through_year}: "
					"that would include data that must stay live."
				)
			self.cutoff_date = cutoff

	def on_update(self):
		from erpnext_data_archiver.archiver.engine import sync_all_archive_tables
		from erpnext_data_archiver.archiver.query_patch import clear_metadata_cache

		clear_metadata_cache()
		if self.enabled:
			sync_all_archive_tables()
