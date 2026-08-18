"""Whitelisted API for Retrieve Archived Data, Archive Settings, and Dagaar controls."""

import json
import os
import subprocess
import sys

import frappe
from frappe.utils import now

from erpnext_data_archiver.archiver import engine, opening_state, preflight, reconcile
from erpnext_data_archiver.archiver.query_patch import (
	get_session_years,
	set_session_years,
)
from erpnext_data_archiver.archiver.report_patches import get_patch_status

MANAGER_ROLES = {"System Manager", "Archive Manager"}
BROWSE_ROLES = MANAGER_ROLES | {"Accounts Manager", "Stock Manager"}
ACTIVE_RUN_STATUSES = (
	"Draft",
	"In Progress",
	"Validating",
	"Snapshotting",
	"Moving",
	"Reconciling",
	"Recovering",
)


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
	require_backup = bool(getattr(settings, "require_backup_before_archive", 1))
	backup_ready = bool(
		getattr(settings, "last_backup_id", None) and getattr(settings, "last_backup_checksum", None)
	)
	return {
		"enabled": bool(settings.enabled),
		"auto_archive": bool(settings.auto_archive),
		"require_backup": require_backup,
		"backup_ready": backup_ready,
		"cutoff_date": str(settings.cutoff_date or engine.compute_cutoff_date(settings)),
		"archive_through_year": getattr(settings, "archive_through_year", None),
		"archivable_years": engine.get_archivable_years(),
		"archived_years": archived_years,
		"session_years": get_session_years(),
		"live_tables": engine.get_live_table_stats(),
		"last_run": _last_run(),
		"active_run": _active_run(),
		"is_manager": bool(MANAGER_ROLES.intersection(set(frappe.get_roles()))),
		"backup_id": getattr(settings, "last_backup_id", None),
		"confirmation_phrase": getattr(settings, "confirmation_phrase", None) or "ARCHIVE",
	}


def _last_run():
	# Prefer a meaningful run (not empty Draft shells)
	rows = frappe.get_all(
		"Archive Run",
		filters={"status": ["in", ["Completed", "Failed", "Moving", "Reconciling", "Validating", "Snapshotting", "Draft"]]},
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


def _active_run():
	rows = frappe.get_all(
		"Archive Run",
		filters={"status": ["in", list(ACTIVE_RUN_STATUSES)]},
		fields=["name", "status", "cutoff_date", "started_on"],
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


def _spawn_engine_call(python_stmt: str) -> int:
	"""Start archive/restore in a new process so the Desk request can return."""
	bench = frappe.utils.get_bench_path()
	sites_path = os.path.join(bench, "sites")
	site = frappe.local.site
	log_dir = os.path.join(bench, "logs")
	os.makedirs(log_dir, exist_ok=True)
	log_path = os.path.join(log_dir, "eda_jobs.log")
	code = (
		"import os\n"
		"import frappe\n"
		f"os.chdir({sites_path!r})\n"
		f"frappe.init(site={site!r}, sites_path={sites_path!r})\n"
		"frappe.connect()\n"
		"try:\n"
		f"    {python_stmt}\n"
		"    frappe.db.commit()\n"
		"except Exception:\n"
		"    frappe.db.rollback()\n"
		"    frappe.log_error(title='erpnext_data_archiver spawned job')\n"
		"    raise\n"
		"finally:\n"
		"    frappe.destroy()\n"
	)
	with open(log_path, "ab") as log:
		proc = subprocess.Popen(
			[sys.executable, "-c", code],
			cwd=bench,
			stdout=log,
			stderr=subprocess.STDOUT,
			start_new_session=True,
			close_fds=True,
			env=os.environ.copy(),
		)
	return proc.pid


@frappe.whitelist()
def confirm_archive(confirmation, fiscal_year=None, run_now=0):
	"""Start archive after typed confirmation. Run now detaches from the HTTP request."""
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
	try:
		preflight.run_preflight(settings, cutoff, require_backup=require_backup)
	except preflight.PreflightError as exc:
		frappe.throw(str(exc))

	fy = fiscal_year or getattr(settings, "archive_through_year", None)
	audit_detail = {"cutoff": str(cutoff), "fiscal_year": fy}

	run = frappe.new_doc("Archive Run")
	run.cutoff_date = cutoff
	run.started_on = now()
	run.schema_version = opening_state.SCHEMA_VERSION
	run.backup_id = getattr(settings, "last_backup_id", None)
	run.backup_checksum = getattr(settings, "last_backup_checksum", None)
	run.insert(ignore_permissions=True)
	frappe.db.commit()

	if int(run_now or 0):
		try:
			pid = _spawn_engine_call(
				"from erpnext_data_archiver.archiver.engine import run_archive; "
				f"run_archive(run_name={run.name!r})"
			)
		except Exception as exc:
			frappe.enqueue(
				"erpnext_data_archiver.archiver.engine.run_archive",
				run_name=run.name,
				queue="long",
				timeout=4 * 60 * 60,
				job_name="erpnext_data_archiver.run_archive",
				enqueue_after_commit=True,
			)
			engine._audit("archive_queued_spawn_failed", frappe.session.user, {**audit_detail, "error": str(exc)})
			return {
				"ok": True,
				"queued": True,
				"run_name": run.name,
				"message": (
					f"Could not start a detached process ({exc}). "
					f"Queued {run.name} instead — start a long-queue worker if it stays Draft."
				),
				"cutoff_date": str(cutoff),
				"fiscal_year": fy,
			}
		engine._audit("archive_started", frappe.session.user, {**audit_detail, "run": run.name, "pid": pid})
		return {
			"ok": True,
			"queued": False,
			"started": True,
			"run_name": run.name,
			"message": f"Archive {run.name} started. Keep this page open — years appear when it finishes.",
			"cutoff_date": str(cutoff),
			"fiscal_year": fy,
		}

	frappe.enqueue(
		"erpnext_data_archiver.archiver.engine.run_archive",
		run_name=run.name,
		queue="long",
		timeout=4 * 60 * 60,
		job_name="erpnext_data_archiver.run_archive",
		enqueue_after_commit=True,
	)
	engine._audit("archive_queued", frappe.session.user, {**audit_detail, "run": run.name})
	return {
		"ok": True,
		"queued": True,
		"run_name": run.name,
		"message": f"Archive {run.name} queued. Start a long-queue worker if status stays Draft.",
		"cutoff_date": str(cutoff),
		"fiscal_year": fy,
	}


@frappe.whitelist()
def run_archive_now(confirmation=None):
	"""Run archive immediately. Confirmation still required when a phrase is set."""
	return confirm_archive(
		confirmation or getattr(engine.get_settings(), "confirmation_phrase", "ARCHIVE"),
		run_now=1,
	)


@frappe.whitelist()
def preview_restore(fiscal_year):
	_check_manager()
	if not fiscal_year:
		frappe.throw("fiscal_year is required")
	return engine.preview_restore(fiscal_year)


@frappe.whitelist()
def restore_year(fiscal_year, force=0, run_now=0):
	"""Queue or run a restore of one archived fiscal year into the live tables."""
	_check_manager()
	if not fiscal_year:
		frappe.throw("fiscal_year is required")
	force = int(force or 0)
	preview = engine.preview_restore(fiscal_year)
	if not preview.get("ok") and not force:
		return {"ok": False, "blocked": True, "preview": preview}

	if int(run_now or 0):
		engine.restore_fiscal_year(fiscal_year, force=bool(force))
		engine._audit("restore_completed_now", fiscal_year, {"force": bool(force)})
		return {
			"ok": True,
			"queued": False,
			"message": f"Restore of {fiscal_year} completed.",
			"preview": preview,
			"archived_years": engine.get_archived_year_stats(),
		}

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
	return {
		"ok": True,
		"queued": True,
		"message": f"Restore of {fiscal_year} queued. Start a long-queue worker or use Run now.",
		"preview": preview,
	}


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
