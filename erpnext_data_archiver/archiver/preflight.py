"""Preflight checks before any live-row deletion (PRE-001 … PRE-008)."""

from __future__ import annotations

import frappe
from frappe.utils import cint, getdate, now_datetime

LOCK_KEY = "eda_archive_job_lock"
SCHEMA_VERSION = "1.0.0"


class PreflightError(frappe.ValidationError):
	pass


def acquire_job_lock(owner: str, ttl: int = 6 * 60 * 60) -> bool:
	"""Acquire exclusive archive/restore lock (same-owner refresh allowed)."""
	cache = frappe.cache()
	key = LOCK_KEY + ":" + frappe.local.site
	existing = cache.get_value(key)
	if existing and existing != owner:
		return False
	# Same owner refreshes TTL; empty key is claimed.
	# NOTE: still a small TOCTOU window under multi-worker — prefer one long queue worker.
	cache.set_value(key, owner, expires_in_sec=ttl)
	return True


def release_job_lock(owner: str) -> None:
	cache = frappe.cache()
	key = LOCK_KEY + ":" + frappe.local.site
	if cache.get_value(key) == owner:
		cache.delete_value(key)


def run_preflight(
	settings=None,
	cutoff=None,
	require_backup: bool = True,
	exclude_run: str | None = None,
	ignore_drafts: bool = False,
	ignore_failed_reposts: bool = False,
) -> dict:
	"""Return a structured preflight report. Raises PreflightError if blocking."""
	from erpnext_data_archiver.archiver.engine import (
		compute_cutoff_date,
		get_enabled_rules,
		get_settings,
	)

	settings = settings or get_settings()
	cutoff = getdate(cutoff or settings.cutoff_date or compute_cutoff_date(settings))
	checks = []
	blocking = []

	def add(code, ok, message, detail=None):
		item = {"code": code, "ok": ok, "message": message, "detail": detail or {}}
		checks.append(item)
		if not ok:
			blocking.append(item)

	# PRE-001 fiscal year / cutoff
	add(
		"PRE-001",
		bool(cutoff),
		f"Cutoff date resolved to {cutoff}",
		{"cutoff": str(cutoff)},
	)
	_check_fy_closed(cutoff, add)

	# PRE-002 drafts in scope (sample high-volume parents)
	_check_drafts(cutoff, add, ignore=ignore_drafts)

	# PRE-003 repost / queue
	_check_repost(add, ignore_failed=ignore_failed_reposts)

	# PRE-004 conflicting job (ignore the run we are validating)
	filters = {
		"status": [
			"in",
			["Validating", "Snapshotting", "Moving", "Reconciling", "In Progress", "Recovering"],
		]
	}
	if exclude_run:
		filters["name"] = ["!=", exclude_run]
	in_progress = frappe.db.exists("Archive Run", filters)
	add(
		"PRE-004",
		not in_progress,
		"No conflicting archive job" if not in_progress else f"Conflicting run: {in_progress}",
	)

	# PRE-005 capacity (rough estimate)
	est_rows = _estimate_rows(cutoff)
	add(
		"PRE-005",
		est_rows >= 0,
		f"Estimated archiveable rows: {est_rows}",
		{"estimated_rows": est_rows},
	)

	# PRE-006 backup reference
	backup_id = getattr(settings, "last_backup_id", None) or ""
	backup_checksum = getattr(settings, "last_backup_checksum", None) or ""
	backup_ok = bool(backup_id and backup_checksum) if require_backup else True
	add(
		"PRE-006",
		backup_ok,
		"Verified backup reference present" if backup_ok else "Set last_backup_id and last_backup_checksum in Archive Settings",
		{"backup_id": backup_id, "backup_checksum": backup_checksum},
	)

	# PRE-007 dependency / rules
	rules = get_enabled_rules()
	add(
		"PRE-007",
		bool(rules),
		f"{len(rules)} enabled DocType rule(s)" if rules else "No enabled DocType rules",
	)

	# PRE-008 enabled flag
	add(
		"PRE-008",
		bool(settings.enabled),
		"Archiving enabled" if settings.enabled else "Enable Archive Settings first",
	)

	report = {
		"ok": not blocking,
		"cutoff": str(cutoff),
		"schema_version": SCHEMA_VERSION,
		"checks": checks,
		"blocking": blocking,
		"generated_on": str(now_datetime()),
	}
	if blocking:
		msgs = "; ".join(f"{b['code']}: {b['message']}" for b in blocking)
		raise PreflightError(f"Preflight failed — {msgs}")
	return report


def preview_counts(cutoff=None) -> dict:
	"""Counts / exclusions for admin preview (no mutation)."""
	from erpnext_data_archiver.archiver.engine import (
		CLOSED_CONDITIONS,
		compute_cutoff_date,
		expanded_rule_doctypes,
		get_enabled_rules,
		get_settings,
	)

	settings = get_settings()
	cutoff = getdate(cutoff or settings.cutoff_date or compute_cutoff_date(settings))
	doctypes = []
	total = 0
	for rule in get_enabled_rules():
		for dt in expanded_rule_doctypes(rule):
			live = "tab" + dt
			if not frappe.db.table_exists(dt):
				continue
			date_field = rule.date_field if rule.doctype_name == dt else "creation"
			if not frappe.db.has_column(dt, date_field):
				# try creation
				date_field = "creation" if frappe.db.has_column(dt, "creation") else None
			if not date_field:
				continue
			where = [f"`{date_field}` < %s"]
			values = [cutoff]
			is_child = dt != rule.doctype_name
			if rule.closed_only and not is_child and frappe.get_meta(dt).is_submittable:
				closed = CLOSED_CONDITIONS.get(dt, "")
				if closed:
					where.append(f"(docstatus = 2 OR (docstatus = 1 AND {closed}))")
			sql = f"SELECT COUNT(*) FROM `{live}` WHERE " + " AND ".join(where)
			count = cint(frappe.db.sql(sql, values)[0][0])
			doctypes.append({"doctype": dt, "rows": count, "parent": rule.doctype_name})
			total += count
	return {"cutoff": str(cutoff), "total_rows": total, "doctypes": doctypes}


def _check_fy_closed(cutoff, add):
	# Soft check: fiscal years ending before cutoff should exist
	try:
		rows = frappe.db.sql(
			"SELECT name, year_end_date, disabled FROM `tabFiscal Year`"
			" WHERE year_end_date < %s ORDER BY year_end_date DESC LIMIT 5",
			(cutoff,),
		)
		add(
			"PRE-001b",
			True,
			f"Found {len(rows)} fiscal year(s) ending before cutoff",
			{"years": [r[0] for r in rows]},
		)
	except Exception as exc:
		add("PRE-001b", False, f"Fiscal Year check failed: {exc}")


def _check_drafts(cutoff, add, ignore=False):
	by_dt = []
	draft_total = 0
	for dt in ("Sales Invoice", "Purchase Invoice", "Journal Entry", "Stock Entry"):
		if not frappe.db.table_exists(dt):
			continue
		if not frappe.db.has_column(dt, "posting_date"):
			continue
		n = cint(
			frappe.db.sql(
				f"SELECT COUNT(*) FROM `tab{dt}` WHERE docstatus = 0 AND posting_date < %s",
				(cutoff,),
			)[0][0]
		)
		if n:
			by_dt.append(f"{dt}: {n}")
			draft_total += n
	ok = draft_total == 0 or ignore
	if draft_total == 0:
		msg = "No in-scope drafts"
	elif ignore:
		msg = f"Ignoring {draft_total} draft document(s) before cutoff ({', '.join(by_dt)})"
	else:
		msg = (
			f"{draft_total} draft document(s) before cutoff ({', '.join(by_dt)}). "
			"Submit or Cancel them, or tick Ignore drafts."
		)
	add("PRE-002", ok, msg, {"drafts": draft_total, "by_doctype": by_dt})


def _check_repost(add, ignore_failed=False):
	skipped = []
	try:
		skipped = skip_queued_reposts()
	except Exception:
		skipped = []
	active = 0
	failed_or_draft = 0
	parts = []
	for dt in ("Repost Accounting Ledger", "Repost Item Valuation"):
		if not frappe.db.exists("DocType", dt):
			continue
		try:
			drafts = cint(frappe.db.count(dt, {"docstatus": 0}))
			queued = cint(
				frappe.db.count(dt, {"docstatus": 1, "status": ["in", ["Queued", "In Progress"]]})
			)
			failed = cint(frappe.db.count(dt, {"docstatus": 1, "status": "Failed"}))
			active += queued
			failed_or_draft += drafts + failed
			if drafts or queued or failed:
				parts.append(f"{dt}: {queued} running, {failed} failed, {drafts} draft")
		except Exception:
			pass
	ok = active == 0
	if skipped:
		msg = f"Skipped {len(skipped)} queued/in-progress repost job(s) so archive does not wait"
	elif active:
		msg = (
			f"{active} repost job(s) still Queued/In Progress"
			+ (f" ({'; '.join(parts)})" if parts else "")
			+ ". Could not skip them automatically."
		)
	else:
		msg = "No pending repost jobs"
	if failed_or_draft and skipped:
		msg += f"; {failed_or_draft} failed/draft repost(s) left as-is"
	add(
		"PRE-003",
		ok,
		msg,
		{
			"active": active,
			"failed_or_draft": failed_or_draft,
			"skipped": skipped,
			"detail": parts,
		},
	)


def skip_queued_reposts() -> list[str]:
	"""Mark Queued/In Progress reposts as Skipped so archive preflight can pass.

	Does not wait for in-flight SQL; operators should only use this on stuck jobs.
	"""
	skipped = []
	for dt in ("Repost Item Valuation", "Repost Accounting Ledger"):
		if not frappe.db.exists("DocType", dt):
			continue
		try:
			rows = frappe.get_all(
				dt,
				filters={"docstatus": 1, "status": ["in", ["Queued", "In Progress"]]},
				fields=["name", "status"],
			)
		except Exception:
			continue
		status_value = "Skipped"
		try:
			meta = frappe.get_meta(dt)
			df = meta.get_field("status")
			options = (df.options or "") if df else ""
			if "Skipped" not in options and "Cancelled" in options:
				status_value = "Cancelled"
			elif "Skipped" not in options:
				status_value = "Failed"
		except Exception:
			pass
		for row in rows:
			frappe.db.set_value(dt, row.name, "status", status_value, update_modified=True)
			skipped.append(f"{dt}:{row.name}:{row.status}->{status_value}")
	if skipped:
		frappe.db.commit()
	return skipped


def _estimate_rows(cutoff) -> int:
	try:
		return preview_counts(cutoff)["total_rows"]
	except Exception:
		return 0
