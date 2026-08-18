"""Scheduled tasks."""

import frappe


ACTIVE_STATUSES = (
	"In Progress",
	"Validating",
	"Snapshotting",
	"Moving",
	"Reconciling",
	"Recovering",
)


def auto_archive_check():
	"""Daily: archive past-FY data, and closed months of the current FY when enabled."""
	try:
		settings = frappe.get_cached_doc("Archive Settings")
	except Exception:
		return
	if not (settings.enabled and settings.auto_archive):
		return

	if frappe.db.exists("Archive Run", {"status": ["in", list(ACTIVE_STATUSES)]}):
		return

	# Auto path still requires backup refs when configured
	if getattr(settings, "require_backup_before_archive", 1):
		if not (settings.last_backup_id and settings.last_backup_checksum):
			frappe.log_error(
				"erpnext_data_archiver: auto archive skipped — backup reference missing"
			)
			return

	from frappe.utils import cint

	from erpnext_data_archiver.archiver import engine

	pending_months = []
	if cint(getattr(settings, "monthly_in_current_year", 0)):
		pending_months = [
			m for m in engine.get_archivable_months() if not m.get("already_archived")
		]
		if pending_months:
			engine.apply_archive_through_month(pending_months[-1]["month"], settings)

	if not pending_months:
		pending_years = [
			y for y in engine.get_archivable_years() if not y.get("already_archived")
		]
		if not pending_years:
			return
		engine.apply_archive_through_year(pending_years[-1]["fiscal_year"], settings)

	frappe.enqueue(
		"erpnext_data_archiver.archiver.engine.run_archive",
		queue="long",
		timeout=4 * 60 * 60,
		job_name="erpnext_data_archiver.run_archive",
		enqueue_after_commit=True,
	)
