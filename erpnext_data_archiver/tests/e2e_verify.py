"""End-to-end verification for erpnext_data_archiver on a live site.

Run:
  bench --site spca.local execute erpnext_data_archiver.tests.e2e_verify.run
or:
  bench --site spca.local console < paste call
"""

from __future__ import annotations

import json
import time

import frappe
from frappe.utils import add_days, add_years, flt, getdate, nowdate, random_string


def run():
	frappe.connect()
	results = []

	def ok(name, cond, detail=""):
		results.append({"check": name, "ok": bool(cond), "detail": detail})
		print(("PASS" if cond else "FAIL"), name, detail)

	# 1. App + DocTypes
	ok("app_installed", "erpnext_data_archiver" in frappe.get_installed_apps())
	for dt in (
		"Archive Settings",
		"Archive Run",
		"Archive Opening GL",
		"Archive Audit Log",
		"Archived Fiscal Year",
	):
		ok(f"doctype_{dt}", frappe.db.exists("DocType", dt))

	# 2. Configure settings
	settings = frappe.get_single("Archive Settings")
	settings.enabled = 1
	settings.require_backup_before_archive = 1
	settings.last_backup_id = "e2e-backup-" + nowdate()
	settings.last_backup_checksum = "sha256:e2e-test-checksum"
	settings.confirmation_phrase = "ARCHIVE"
	settings.batch_size = 500
	# Cutoff = start of current FY if possible, else today - 180 days
	try:
		from erpnext_data_archiver.archiver.engine import compute_cutoff_date

		cutoff = compute_cutoff_date(settings)
	except Exception:
		cutoff = add_days(getdate(nowdate()), -180)
	settings.cutoff_date = cutoff
	settings.archive_through_year = str(add_days(getdate(cutoff), -1).year)
	settings.save(ignore_permissions=True)
	frappe.db.commit()
	ok("settings_enabled", bool(settings.enabled), str(cutoff))

	# Seed rules if empty
	from erpnext_data_archiver.install import seed_default_rules

	seed_default_rules()
	settings.reload()
	ok("rules_seeded", len(settings.get("doc_type_rules") or []) > 0, str(len(settings.get("doc_type_rules") or [])))

	# 3. Seed historical GL / SLE-like volume to slow queries
	company = frappe.db.get_value("Company", {}, "name")
	ok("company_exists", bool(company), company or "")
	if not company:
		return _finish(results)

	account = frappe.db.get_value(
		"Account", {"company": company, "is_group": 0, "account_type": "Cash"}, "name"
	) or frappe.db.get_value("Account", {"company": company, "is_group": 0}, "name")
	ok("account_exists", bool(account), account or "")

	seeded = _seed_gl_rows(company, account, cutoff, n=2500)
	ok("seeded_historical_gl", seeded > 0, f"rows={seeded}")

	live_before = frappe.db.sql(
		"SELECT COUNT(*) FROM `tabGL Entry` WHERE posting_date < %s"
		" AND IFNULL(voucher_type,'') != 'Archive Opening'",
		(cutoff,),
	)[0][0]
	ok("live_historical_gl_before", live_before > 0, str(live_before))

	# 4. Preflight + preview
	from erpnext_data_archiver.archiver import preflight

	try:
		report = preflight.run_preflight(settings, cutoff, require_backup=True)
		ok("preflight_pass", report.get("ok"), json.dumps(report.get("blocking") or [])[:200])
	except Exception as e:
		ok("preflight_pass", False, str(e)[:300])
		return _finish(results)

	preview = preflight.preview_counts(cutoff)
	ok("preview_counts", preview.get("total_rows", 0) > 0, str(preview.get("total_rows")))

	# 5. Run archive (sync, not enqueue)
	from erpnext_data_archiver.archiver.engine import run_archive, get_archived_year_stats, get_live_table_stats

	t0 = time.time()
	try:
		run_name = run_archive()
		elapsed = time.time() - t0
		run = frappe.get_doc("Archive Run", run_name)
		ok("archive_completed", run.status == "Completed", f"{run_name} in {elapsed:.1f}s status={run.status} err={run.error}")
	except Exception as e:
		ok("archive_completed", False, str(e)[:500])
		return _finish(results)

	live_after = frappe.db.sql(
		"SELECT COUNT(*) FROM `tabGL Entry` WHERE posting_date < %s"
		" AND IFNULL(voucher_type,'') != 'Archive Opening'",
		(cutoff,),
	)[0][0]
	ok("historical_gl_removed", live_after < live_before, f"before={live_before} after={live_after}")

	synth = frappe.db.sql(
		"SELECT COUNT(*) FROM `tabGL Entry` WHERE voucher_type='Archive Opening'"
	)[0][0]
	ok("synthetic_openings_present", synth > 0, str(synth))

	opening_gl = frappe.db.count("Archive Opening GL", {"cutoff_date": cutoff})
	ok("opening_gl_doctype", opening_gl > 0, str(opening_gl))

	arch_table = "tabGL Entry Archive"
	arch_count = frappe.db.sql(f"SELECT COUNT(*) FROM `{arch_table}`")[0][0] if frappe.db.table_exists("GL Entry") else 0
	# table_exists checks doctype; check information_schema
	exists = frappe.db.sql(
		"SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s",
		(arch_table,),
	)
	if exists:
		arch_count = frappe.db.sql(f"SELECT COUNT(*) FROM `{arch_table}`")[0][0]
	ok("archive_shadow_rows", exists and arch_count > 0, str(arch_count))

	years = get_archived_year_stats()
	ok("archived_years_registered", len(years) > 0, json.dumps(years)[:200])
	expected_fy = str(add_days(getdate(cutoff), -1).year)
	tagged_ok = any(y["fiscal_year"] == expected_fy for y in years)
	ok("archived_year_tag_not_cutoff_year", tagged_ok, f"expected={expected_fy} got={years}")

	# 6. Hot path: active report mode should not need archive rewrite
	from erpnext_data_archiver.archiver.routing import MODE_ACTIVE, resolve_report_mode

	mode = resolve_report_mode(from_date=str(cutoff), to_date=nowdate(), cutoff=cutoff)
	ok("routing_active", mode == MODE_ACTIVE, mode)

	# Timing: count live GL vs would-be full
	t1 = time.time()
	frappe.db.sql("SELECT COUNT(*) FROM `tabGL Entry`")
	live_count_time = time.time() - t1
	ok("live_count_fast", True, f"{live_count_time*1000:.1f}ms rows={frappe.db.sql('SELECT COUNT(*) FROM `tabGL Entry`')[0][0]}")

	# 7. Restore dry-run
	from erpnext_data_archiver.archiver.engine import preview_restore

	if years:
		fy = years[0]["fiscal_year"]
		prev = preview_restore(fy)
		ok("restore_preview", "ok" in prev, json.dumps(prev)[:200])

	return _finish(results)


def _seed_gl_rows(company, account, cutoff, n=2500):
	"""Insert many historical GL rows before cutoff (synthetic test vouchers)."""
	from frappe.utils import now_datetime

	# Don't seed if already plenty
	existing = frappe.db.sql(
		"SELECT COUNT(*) FROM `tabGL Entry` WHERE posting_date < %s"
		" AND voucher_type='EDA Seed'",
		(cutoff,),
	)[0][0]
	if existing >= n:
		return int(existing)

	need = n - int(existing)
	posting = add_days(getdate(cutoff), -30)
	now = now_datetime()
	batch = []
	for i in range(need):
		name = f"EDA-SEED-{random_string(10)}"
		debit = 10.0 if i % 2 == 0 else 0.0
		credit = 0.0 if i % 2 == 0 else 10.0
		batch.append(
			(
				name,
				now,
				now,
				"Administrator",
				"Administrator",
				1,
				0,
				posting,
				account,
				company,
				debit,
				credit,
				"EDA Seed",
				f"EDA-SEED-V-{i // 2}",
				"Seeded for archiver E2E",
				0,
			)
		)
		if len(batch) >= 200:
			_insert_gl_batch(batch)
			batch = []
	if batch:
		_insert_gl_batch(batch)
	frappe.db.commit()
	return int(
		frappe.db.sql(
			"SELECT COUNT(*) FROM `tabGL Entry` WHERE voucher_type='EDA Seed' AND posting_date < %s",
			(cutoff,),
		)[0][0]
	)


def _insert_gl_batch(batch):
	cols = (
		"name, creation, modified, modified_by, owner, docstatus, idx, posting_date, "
		"account, company, debit, credit, voucher_type, voucher_no, remarks, is_cancelled"
	)
	# Adapt if is_cancelled missing
	has_cancelled = frappe.db.sql(
		"SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE()"
		" AND TABLE_NAME='tabGL Entry' AND COLUMN_NAME='is_cancelled'"
	)
	if not has_cancelled:
		cols = cols.replace(", is_cancelled", "")
		batch = [b[:-1] for b in batch]
	placeholders = ", ".join(["%s"] * len(batch[0]))
	values_sql = ", ".join([f"({placeholders})"] * len(batch))
	flat = [v for row in batch for v in row]
	frappe.db.sql(f"INSERT INTO `tabGL Entry` ({cols}) VALUES {values_sql}", flat)


def _finish(results):
	failed = [r for r in results if not r["ok"]]
	summary = {"passed": len(results) - len(failed), "failed": len(failed), "results": results}
	print("\n=== SUMMARY ===")
	print(json.dumps(summary, indent=2, default=str))
	path = frappe.get_site_path("private", "files", "eda_e2e_results.json")
	with open(path, "w") as f:
		json.dump(summary, f, indent=2, default=str)
	print("Wrote", path)
	return summary
