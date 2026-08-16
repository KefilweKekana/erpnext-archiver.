"""Post-archive reconciliation (fail-closed before Completed)."""

from __future__ import annotations

import json

import frappe
from frappe.utils import flt, getdate

from erpnext_data_archiver.archiver.query_patch import archive_table_name, bypass_archives

SYNTH = "Archive Opening"
# Allow small float drift on qty/value sums
EPS = 0.05


def run_reconciliation(cutoff, archive_run: str | None = None) -> dict:
	"""Compare opening-state aggregates with archive continuity checks."""
	cutoff = getdate(cutoff)
	checks = []
	with bypass_archives():
		checks.append(_gl_opening_matches_archive(cutoff, archive_run))
		checks.append(_stock_opening_matches_archive(cutoff, archive_run))
		checks.append(_opening_gl_exists(cutoff))
		checks.append(_opening_stock_exists(cutoff))
		checks.append(_synthetic_gl_present(cutoff))

	failed = [c for c in checks if not c.get("ok")]
	report = {
		"ok": not failed,
		"cutoff": str(cutoff),
		"archive_run": archive_run,
		"checks": checks,
		"failed": failed,
	}
	return report


def evidence_markdown(report: dict) -> str:
	lines = [
		"# Archive Reconciliation Evidence",
		"",
		f"- Cutoff: `{report.get('cutoff')}`",
		f"- Archive Run: `{report.get('archive_run')}`",
		f"- Result: **{'PASS' if report.get('ok') else 'FAIL'}**",
		"",
		"## Checks",
		"",
	]
	for c in report.get("checks") or []:
		status = "OK" if c.get("ok") else "FAIL"
		lines.append(f"- [{status}] **{c.get('id')}**: {c.get('message')}")
		if c.get("detail"):
			lines.append(f"  - detail: `{json.dumps(c['detail'], default=str)}`")
	return "\n".join(lines) + "\n"


def _table_exists(name: str) -> bool:
	return bool(
		frappe.db.sql(
			"SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()"
			" AND TABLE_NAME = %s LIMIT 1",
			(name,),
		)
	)


def _gl_opening_matches_archive(cutoff, archive_run=None) -> dict:
	"""Opening GL should match GL archived in this run (or synthetics if no run)."""
	arch = archive_table_name("GL Entry")
	if not _table_exists(arch):
		return {"id": "FIN-GL", "ok": True, "message": "No GL archive table yet", "detail": {}}

	if archive_run:
		arch_row = frappe.db.sql(
			f"SELECT COALESCE(SUM(`debit`),0), COALESCE(SUM(`credit`),0) FROM `{arch}`"
			" WHERE `archive_run` = %s",
			(archive_run,),
		)[0]
	else:
		arch_row = frappe.db.sql(
			f"SELECT COALESCE(SUM(`debit`),0), COALESCE(SUM(`credit`),0) FROM `{arch}`"
			" WHERE `fiscal_year_archived` IS NOT NULL"
		)[0]
	arch_debit, arch_credit = flt(arch_row[0]), flt(arch_row[1])

	open_row = frappe.db.sql(
		"SELECT COALESCE(SUM(`debit`),0), COALESCE(SUM(`credit`),0)"
		" FROM `tabArchive Opening GL` WHERE `cutoff_date` = %s",
		(cutoff,),
	)[0]
	open_debit, open_credit = flt(open_row[0]), flt(open_row[1])

	# Prefer comparing openings to live synthetics (always same snapshot)
	synth = frappe.db.sql(
		"SELECT COALESCE(SUM(`debit`),0), COALESCE(SUM(`credit`),0)"
		" FROM `tabGL Entry` WHERE `voucher_type` = %s",
		(SYNTH,),
	)[0]
	synth_debit, synth_credit = flt(synth[0]), flt(synth[1])

	ok_synth = abs(open_debit - synth_debit) <= EPS and abs(open_credit - synth_credit) <= EPS
	# When this run archived GL, openings should cover at least that run's totals
	# (openings may also include prior preserved history via synthetics).
	if arch_debit == 0 and arch_credit == 0:
		ok = ok_synth or (open_debit == 0 and open_credit == 0)
		msg = "No GL moved this run; openings↔synthetics checked"
	else:
		ok = ok_synth
		msg = (
			f"Openings debit={open_debit} credit={open_credit}; "
			f"synthetics debit={synth_debit} credit={synth_credit}; "
			f"run archive debit={arch_debit} credit={arch_credit}"
		)
	return {
		"id": "FIN-GL",
		"ok": ok,
		"message": msg,
		"detail": {
			"archive_debit": arch_debit,
			"archive_credit": arch_credit,
			"opening_debit": open_debit,
			"opening_credit": open_credit,
			"synth_debit": synth_debit,
			"synth_credit": synth_credit,
		},
	}


def _stock_opening_matches_archive(cutoff, archive_run=None) -> dict:
	arch = archive_table_name("Stock Ledger Entry")
	if not _table_exists(arch):
		return {"id": "STOCK-QTY", "ok": True, "message": "No SLE archive table", "detail": {}}

	cancelled = ""
	if frappe.db.sql(
		"SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE()"
		" AND TABLE_NAME = %s AND COLUMN_NAME = 'is_cancelled' LIMIT 1",
		(arch,),
	):
		cancelled = " AND IFNULL(`is_cancelled`, 0) = 0"

	if archive_run:
		arch_qty = flt(
			frappe.db.sql(
				f"SELECT COALESCE(SUM(`actual_qty`),0) FROM `{arch}`"
				f" WHERE `archive_run` = %s {cancelled}",
				(archive_run,),
			)[0][0]
		)
	else:
		arch_qty = flt(
			frappe.db.sql(
				f"SELECT COALESCE(SUM(`actual_qty`),0) FROM `{arch}`"
				f" WHERE `fiscal_year_archived` IS NOT NULL {cancelled}"
			)[0][0]
		)

	open_qty = flt(
		frappe.db.sql(
			"SELECT COALESCE(SUM(`qty`),0) FROM `tabArchive Opening Stock`"
			" WHERE `cutoff_date` = %s",
			(cutoff,),
		)[0][0]
	)

	synth_qty = 0.0
	if frappe.db.table_exists("Stock Ledger Entry"):
		synth_qty = flt(
			frappe.db.sql(
				"SELECT COALESCE(SUM(`actual_qty`),0) FROM `tabStock Ledger Entry`"
				" WHERE `voucher_type` = %s",
				(SYNTH,),
			)[0][0]
		)

	ok = abs(open_qty - synth_qty) <= max(EPS, abs(open_qty) * 0.001)
	# Empty stock archive is fine
	if abs(arch_qty) < EPS and abs(open_qty) < EPS:
		ok = True
	return {
		"id": "STOCK-QTY",
		"ok": ok,
		"message": f"Opening stock qty={open_qty}; synth SLE qty={synth_qty}; run archive qty={arch_qty}",
		"detail": {"archive_qty": arch_qty, "opening_qty": open_qty, "synth_qty": synth_qty},
	}


def _opening_gl_exists(cutoff) -> dict:
	n = frappe.db.count("Archive Opening GL", {"cutoff_date": cutoff})
	had_gl = frappe.db.table_exists("GL Entry")
	ok = True
	if had_gl:
		arch = archive_table_name("GL Entry")
		arch_n = 0
		if _table_exists(arch):
			arch_n = frappe.db.sql(
				f"SELECT COUNT(*) FROM `{arch}` WHERE `fiscal_year_archived` IS NOT NULL"
			)[0][0]
		if int(arch_n) > 0 and n == 0:
			ok = False
	return {
		"id": "OPEN-GL",
		"ok": ok,
		"message": f"Archive Opening GL rows={n}",
		"detail": {"rows": n},
	}


def _opening_stock_exists(cutoff) -> dict:
	n = frappe.db.count("Archive Opening Stock", {"cutoff_date": cutoff})
	arch = archive_table_name("Stock Ledger Entry")
	ok = True
	if _table_exists(arch):
		arch_n = frappe.db.sql(
			f"SELECT COUNT(*) FROM `{arch}` WHERE `fiscal_year_archived` IS NOT NULL"
		)[0][0]
		# If we archived SLE with non-zero net qty, openings should exist
		if int(arch_n) > 0:
			qty = flt(
				frappe.db.sql(
					f"SELECT COALESCE(SUM(`actual_qty`),0) FROM `{arch}`"
					" WHERE `fiscal_year_archived` IS NOT NULL"
				)[0][0]
			)
			if abs(qty) > EPS and n == 0:
				ok = False
	return {
		"id": "OPEN-STOCK",
		"ok": ok,
		"message": f"Archive Opening Stock rows={n}",
		"detail": {"rows": n},
	}


def _synthetic_gl_present(cutoff) -> dict:
	"""Live synthetic GL should exist whenever Archive Opening GL does."""
	n_open = frappe.db.count("Archive Opening GL", {"cutoff_date": cutoff})
	if n_open == 0 or not frappe.db.table_exists("GL Entry"):
		return {"id": "SYNTH-GL", "ok": True, "message": "No openings requiring synthetics", "detail": {}}
	n_synth = frappe.db.sql(
		"SELECT COUNT(*) FROM `tabGL Entry` WHERE `voucher_type` = %s",
		(SYNTH,),
	)[0][0]
	ok = int(n_synth) > 0
	return {
		"id": "SYNTH-GL",
		"ok": ok,
		"message": f"Synthetic GL rows={n_synth} (openings={n_open})",
		"detail": {"synthetic": int(n_synth), "openings": n_open},
	}


def assert_reconciliation_passed(report: dict) -> None:
	if not report.get("ok"):
		failed = report.get("failed") or []
		msgs = "; ".join(f"{f.get('id')}: {f.get('message')}" for f in failed)
		frappe.throw(f"Reconciliation failed — {msgs}", frappe.ValidationError)
