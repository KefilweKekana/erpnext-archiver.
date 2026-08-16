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
	"""Daily: archive past-fiscal-year data when auto archiving is enabled."""
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

	frappe.enqueue(
		"erpnext_data_archiver.archiver.engine.run_archive",
		queue="long",
		timeout=4 * 60 * 60,
		job_name="erpnext_data_archiver.run_archive",
		enqueue_after_commit=True,
	)
