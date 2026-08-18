"""Install / migrate / uninstall hooks."""

import frappe

from erpnext_data_archiver.archiver.engine import DEFAULT_RULES, sync_all_archive_tables
from erpnext_data_archiver.archiver.query_patch import clear_metadata_cache

ROLE = "Archive Manager"


def after_install():
	create_archive_manager_role()
	try:
		seed_default_rules()
	except Exception:
		# DocTypes may not be fully importable until migrate finishes; seed again in after_migrate.
		frappe.log_error("erpnext_data_archiver: seed_default_rules deferred to migrate")
	try:
		sync_all_archive_tables()
	except Exception:
		frappe.log_error("erpnext_data_archiver: sync_all_archive_tables deferred to migrate")


def after_migrate():
	try:
		seed_default_rules()
	except Exception:
		frappe.log_error("erpnext_data_archiver: seed_default_rules failed after migrate")
	sync_all_archive_tables()
	try:
		from erpnext_data_archiver.archiver.engine import retag_child_archive_years

		retag_child_archive_years()
	except Exception:
		frappe.log_error("erpnext_data_archiver: retag_child_archive_years failed after migrate")


def before_uninstall():
	"""Block uninstall while archive sets remain (Dagaar restore/retention gate)."""
	force = frappe.conf.get("eda_force_uninstall")
	if force:
		return
	if frappe.db.exists("DocType", "Archived Fiscal Year"):
		remaining = frappe.db.count("Archived Fiscal Year")
		if remaining:
			frappe.throw(
				f"Cannot uninstall erpnext_data_archiver: {remaining} archived fiscal year(s) "
				"still registered. Restore or export them first, or set "
				"eda_force_uninstall in site_config.json after retention approval."
			)
	# Also block when shadow tables still hold rows (registry may be empty)
	shadow_rows = frappe.db.sql(
		"""
		SELECT TABLE_NAME, TABLE_ROWS
		FROM information_schema.TABLES
		WHERE TABLE_SCHEMA = DATABASE()
		  AND TABLE_NAME LIKE '% Archive'
		  AND IFNULL(TABLE_ROWS, 0) > 0
		LIMIT 20
		"""
	)
	if shadow_rows:
		sample = ", ".join(f"{n} (~{c})" for n, c in shadow_rows[:5])
		frappe.throw(
			"Cannot uninstall erpnext_data_archiver: archive shadow tables still contain rows "
			f"({sample}). Restore/export first, or set eda_force_uninstall after approval."
		)


def create_archive_manager_role():
	if not frappe.db.exists("Role", ROLE):
		role = frappe.new_doc("Role")
		role.role_name = ROLE
		role.desk_access = 1
		role.insert(ignore_permissions=True)
		frappe.db.commit()


def seed_default_rules():
	settings = frappe.get_single("Archive Settings")
	existing = {r.doctype_name for r in settings.get("doc_type_rules") or []}
	added = False
	for doctype, date_field, closed_only in DEFAULT_RULES:
		if doctype in existing or not frappe.db.exists("DocType", doctype):
			continue
		settings.append(
			"doc_type_rules",
			{
				"doctype_name": doctype,
				"date_field": date_field,
				"closed_only": closed_only,
				"enabled": 1,
				"archive_children": 1,
				"archive_cancelled": 1,
			},
		)
		added = True
	if added:
		settings.save(ignore_permissions=True)
		frappe.db.commit()
	clear_metadata_cache()
