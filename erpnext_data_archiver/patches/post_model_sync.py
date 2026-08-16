# Frappe executes every line of patches.txt after model sync during migrate.
# The archive shadow tables must track the live schema, so re-sync them here.
import frappe


def execute():
    try:
        from erpnext_data_archiver.archiver.engine import sync_all_archive_tables

        if "erpnext_data_archiver" in (frappe.get_installed_apps() or []):
            sync_all_archive_tables()
    except Exception:
        frappe.log_error("erpnext_data_archiver: post_model_sync patch failed")
