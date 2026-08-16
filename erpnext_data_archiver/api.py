"""Whitelisted API for Retrieve Archived Data, Archive Settings, and Dagaar controls."""

import json

import frappe

from erpnext_data_archiver.archiver import engine, preflight, reconcile
from erpnext_data_archiver.archiver.query_patch import (
	get_session_years,
	set_session_years,
)
from erpnext_data_archiver.archiver.report_patches import get_patch_status

MANAGER_ROLES = {"System Manager", "Archive Manager"}
BROWSE_ROLES = MANAGER_ROLES | {"Accounts Manager", "Stock Manager"}


def _check_manager():
	if not MANAGER_ROLES.intersection(set(frappe.get_roles())):
		frappe.throw(
			"You need the Archive Manager or System Manager role.",
			frappe.PermissionError,
		)


def _check_browse():
	if not BROWSE_ROLES.intersection(set(frappe.get_roles())):
		frappe.throw("Insufficient permission to browse archive state.", frappe.PermissionError)


@frappe.whitelist()
def get_state():
	"""Everything the retrieval page needs in one round trip."""
	_check_browse()
	settings = engine.get_settings()
	archived_years = engine.get_archived_year_stats()
	return {
		"enabled": bool(settings.enabled),
		"auto_archive": bool(settings.auto_archive),
		"cutoff_date": str(settings.cutoff_date or engine.compute_cutoff_date(settings)),
		"archive_through_year": getattr(settings, "archive_through_year", None),
		"archivable_years": engine.get_archivable_years(),
		"archived_years": archived_years,
		"session_years": get_session_years(),
		"live_tables": engine.get_live_table_stats(),
		"last_run": _last_run(),
		"is_manager": bool(MANAGER_ROLES.intersection(set(frappe.get_roles()))),
		"backup_id": getattr(settings, "last_backup_id", None),
		"confirmation_phrase": getattr(settings, "confirmation_phrase", None) or "ARCHIVE",
	}


def _last_run():
	# Prefer a meaningful run (not empty Draft shells)
	rows = frappe.get_all(
		"Archive Run",
		filters={"status": ["in", ["Completed", "Failed", "Moving", "Reconciling", "Validating", "Snapshotting"]]},
		fields=["name", "status", "cutoff_date", "started_on", "completed_on"],
		order_by="creation desc",
		limit=1,
	)
	if rows:
		return rows[0]
	rows = frappe.get_all(
		"Archive Run",
		fields=["name", "status", "cutoff_date", "started_on", "completed_on"],
		order_by="creation desc",
		limit=1,
	)
	return rows[0] if rows else None


@frappe.whitelist()
def activate_archive_years(years):
	"""Include the selected archived fiscal years in this user's session."""
	_check_browse()
	if isinstance(years, str):
		years = json.loads(years)
	years = [str(y) for y in (years or [])]

	valid = {y["fiscal_year"] for y in engine.get_archived_year_stats()}
	unknown = [y for y in years if y not in valid]
	if unknown:
		frappe.throw("Unknown archived fiscal year(s): " + ", ".join(unknown))

	set_session_years(frappe.session.user, years)
	engine._audit("browse_activate", frappe.session.user, {"years": years})
	return {"ok": True, "session_years": years}


@frappe.whitelist()
def deactivate_archive_years():
	"""Return the session to live-only data."""
	_check_browse()
	set_session_years(frappe.session.user, [])
	engine._audit("browse_deactivate", frappe.session.user, {})
	return {"ok": True, "session_years": []}


@frappe.whitelist()
def preview_archive(fiscal_year=None):
	"""Preflight + row counts without mutating data."""
	_check_manager()
	settings = engine.get_settings()
	if fiscal_year:
		from erpnext_data_archiver.archiver import fiscal

		cutoff = fiscal.cutoff_after_fiscal_year(fiscal_year)
	else:
		cutoff = settings.cutoff_date or engine.compute_cutoff_date(settings)
	require_backup = bool(getattr(settings, "require_backup_before_archive", 1))
	try:
		report = preflight.run_preflight(settings, cutoff, require_backup=require_backup)
		ok = True
		error = None
	except preflight.PreflightError as exc:
		report = {"ok": False, "message": str(exc)}
		ok = False
		error = str(exc)
	counts = preflight.preview_counts(cutoff)
	return {
		"ok": ok,
		"error": error,
		"preflight": report,
		"preview": counts,
		"fiscal_year": fiscal_year or getattr(settings, "archive_through_year", None),
		"cutoff_date": str(cutoff),
	}


@frappe.whitelist()
def confirm_archive(confirmation, fiscal_year=None):
	"""Enqueue archive after typed confirmation phrase matches settings."""
	_check_manager()
	settings = engine.get_settings()
	phrase = (getattr(settings, "confirmation_phrase", None) or "ARCHIVE").strip()
	if (confirmation or "").strip() != phrase:
		frappe.throw(f"Confirmation phrase must be exactly: {phrase}")

	if fiscal_year:
		cutoff = engine.apply_archive_through_year(fiscal_year, settings)
	elif getattr(settings, "archive_through_year", None):
		cutoff = engine.apply_archive_through_year(settings.archive_through_year, settings)
	else:
		cutoff = settings.cutoff_date or engine.compute_cutoff_date(settings)

	require_backup = bool(getattr(settings, "require_backup_before_archive", 1))
	preflight.run_preflight(settings, cutoff, require_backup=require_backup)

	frappe.enqueue(
		"erpnext_data_archiver.archiver.engine.run_archive",
		queue="long",
		timeout=4 * 60 * 60,
		job_name="erpnext_data_archiver.run_archive",
		enqueue_after_commit=True,
	)
	engine._audit(
		"archive_queued",
		frappe.session.user,
		{
			"cutoff": str(cutoff),
			"fiscal_year": fiscal_year or getattr(settings, "archive_through_year", None),
		},
	)
	return {
		"ok": True,
		"message": "Archive run queued in the background.",
		"cutoff_date": str(cutoff),
		"fiscal_year": fiscal_year or getattr(settings, "archive_through_year", None),
	}


@frappe.whitelist()
def run_archive_now(confirmation=None):
	"""Backward-compatible entry; requires confirmation when phrase is set."""
	return confirm_archive(confirmation or getattr(engine.get_settings(), "confirmation_phrase", "ARCHIVE"))


@frappe.whitelist()
def preview_restore(fiscal_year):
	_check_manager()
	if not fiscal_year:
		frappe.throw("fiscal_year is required")
	return engine.preview_restore(fiscal_year)


@frappe.whitelist()
def restore_year(fiscal_year, force=0):
	"""Enqueue a restore of one archived fiscal year into the live tables."""
	_check_manager()
	if not fiscal_year:
		frappe.throw("fiscal_year is required")
	force = int(force or 0)
	preview = engine.preview_restore(fiscal_year)
	if not preview.get("ok") and not force:
		return {"ok": False, "blocked": True, "preview": preview}

	frappe.enqueue(
		"erpnext_data_archiver.archiver.engine.restore_fiscal_year",
		fiscal_year=fiscal_year,
		force=bool(force),
		queue="long",
		timeout=4 * 60 * 60,
		job_name=f"erpnext_data_archiver.restore.{fiscal_year}",
		enqueue_after_commit=True,
	)
	engine._audit("restore_queued", fiscal_year, {"force": bool(force)})
	return {"ok": True, "message": f"Restore of {fiscal_year} queued.", "preview": preview}


@frappe.whitelist()
def get_reconciliation_evidence(run_name):
	_check_manager()
	run = frappe.get_doc("Archive Run", run_name)
	raw = run.reconciliation_report or "{}"
	try:
		report = json.loads(raw)
	except Exception:
		report = {"ok": False, "raw": raw}
	return {
		"report": report,
		"markdown": reconcile.evidence_markdown(report if isinstance(report, dict) else {"ok": False}),
	}


@frappe.whitelist()
def get_diagnostics():
	"""Which report entry points were wrapped (visible in Archive Settings)."""
	_check_manager()
	return get_patch_status()


def boot_session(bootinfo):
	"""Expose the archive session state to Desk (navbar indicator)."""
	try:
		enabled = bool(frappe.db.get_single_value("Archive Settings", "enabled"))
	except Exception:
		enabled = False
	try:
		bootinfo["archiver"] = {
			"session_years": get_session_years(),
			"enabled": enabled,
		}
	except Exception:
		bootinfo["archiver"] = {"session_years": [], "enabled": enabled}
