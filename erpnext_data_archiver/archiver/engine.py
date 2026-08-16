"""Archiving engine: schema sync, preflight, opening state, journaled move, restore.

Data older than the cutoff is copied in verified batches into shadow
``<table> Archive`` tables and then deleted from live tables. Opening-state
snapshots keep current-period accounting/stock correct without scanning
archives. Only MariaDB/MySQL is supported.
"""

from __future__ import annotations

import json

import frappe
from frappe.utils import add_days, cint, getdate, now, now_datetime

from erpnext_data_archiver.archiver import fiscal, manifest, opening_state, preflight, reconcile
from erpnext_data_archiver.archiver.query_patch import (
	archive_table_name,
	bypass_archives,
	clear_metadata_cache,
)

METADATA_COLUMNS = (
	("archived_on", "DATETIME(6) NULL"),
	("archive_run", "VARCHAR(140) NULL"),
	("fiscal_year_archived", "VARCHAR(140) NULL"),
)

CLOSED_CONDITIONS = {
	"Sales Invoice": "`outstanding_amount` = 0",
	"POS Invoice": "`outstanding_amount` = 0",
	"Purchase Invoice": "`outstanding_amount` = 0",
	"Sales Order": "`status` IN ('Completed', 'Closed', 'Cancelled')",
	"Purchase Order": "`status` IN ('Completed', 'Closed', 'Cancelled')",
	"Delivery Note": "`status` IN ('Completed', 'Closed', 'Cancelled')",
	"Purchase Receipt": "`status` IN ('Completed', 'Closed', 'Cancelled')",
	"Quotation": "`status` IN ('Ordered', 'Lost', 'Cancelled', 'Expired')",
	"POS Invoice Merge Log": "1 = 1",
}

DEFAULT_RULES = [
	("GL Entry", "posting_date", 0),
	("Payment Ledger Entry", "posting_date", 0),
	("Stock Ledger Entry", "posting_date", 0),
	("Sales Invoice", "posting_date", 1),
	("POS Invoice", "posting_date", 1),
	("Purchase Invoice", "posting_date", 1),
	("Payment Entry", "posting_date", 0),
	("Journal Entry", "posting_date", 0),
	("Sales Order", "transaction_date", 1),
	("Purchase Order", "transaction_date", 1),
	("Delivery Note", "posting_date", 1),
	("Purchase Receipt", "posting_date", 1),
	("Stock Entry", "posting_date", 0),
	("Stock Reconciliation", "posting_date", 0),
	("Quotation", "transaction_date", 1),
	("Supplier Quotation", "transaction_date", 0),
]

VALID_TRANSITIONS = {
	"Draft": {"Validating", "Failed"},
	"Validating": {"Snapshotting", "Failed"},
	"Snapshotting": {"Moving", "Failed"},
	"Moving": {"Reconciling", "Failed", "Recovering"},
	"Reconciling": {"Completed", "Failed", "Recovering"},
	"Recovering": {"Failed", "Completed"},
	"In Progress": {"Completed", "Failed"},  # legacy
	"Failed": {"Validating", "Recovering"},
	"Completed": set(),
}


class UnsupportedDatabase(frappe.ValidationError):
	pass


def get_settings():
	return frappe.get_cached_doc("Archive Settings")


def ensure_mariadb():
	if (frappe.conf.get("db_type") or "mariadb").lower() not in ("mariadb", "mysql"):
		raise UnsupportedDatabase(
			"erpnext_data_archiver currently supports MariaDB/MySQL sites only."
		)


def compute_cutoff_date(settings=None):
	return fiscal.current_fy_start()


def get_enabled_rules():
	settings = get_settings()
	return [r for r in (settings.get("doc_type_rules") or []) if r.enabled]


def expanded_rule_doctypes(rule):
	names = [rule.doctype_name]
	if rule.archive_children:
		try:
			meta = frappe.get_meta(rule.doctype_name)
			names.extend(d.options for d in meta.get_table_fields())
		except Exception:
			pass
	return list(dict.fromkeys(names))


def parent_field_for_child(parent_doctype, child_doctype):
	"""Return the child table field that links to the parent, if any."""
	try:
		meta = frappe.get_meta(child_doctype)
		for df in meta.fields:
			if df.fieldtype == "Link" and df.options == parent_doctype and df.fieldname in (
				"parent",
			):
				return "parent"
		# Standard child tables use parent + parenttype
		if frappe.db.has_column(child_doctype, "parent"):
			return "parent"
	except Exception:
		pass
	return "parent" if frappe.db.has_column(child_doctype, "parent") else None


# ---------------------------------------------------------------------------
# Schema synchronisation
# ---------------------------------------------------------------------------

def ensure_archive_table(doctype):
	ensure_mariadb()
	live = "tab" + doctype
	arch = archive_table_name(doctype)

	with bypass_archives():
		if not _table_exists(live):
			return arch
		if not _table_exists(arch):
			frappe.db.sql(f"CREATE TABLE `{arch}` LIKE `{live}`")

		for col, definition in METADATA_COLUMNS:
			if not _column_exists(arch, col):
				frappe.db.sql(f"ALTER TABLE `{arch}` ADD COLUMN `{col}` {definition}")

		for col, definition in _missing_live_columns(live, arch):
			frappe.db.sql(f"ALTER TABLE `{arch}` ADD COLUMN `{col}` {definition}")

		_ensure_index(arch, "fiscal_year_archived", ["fiscal_year_archived"])
		date_field = _date_field_for(doctype)
		if date_field and _column_exists(arch, date_field):
			_ensure_index(arch, "eda_date_idx", ["fiscal_year_archived", date_field])
	return arch


def sync_all_archive_tables():
	try:
		get_settings()
	except Exception:
		return
	for rule in get_enabled_rules():
		for dt in expanded_rule_doctypes(rule):
			try:
				ensure_archive_table(dt)
			except Exception:
				frappe.log_error(f"erpnext_data_archiver: failed to sync archive table for {dt}")
	clear_metadata_cache()


def _table_exists(table):
	return bool(
		frappe.db.sql(
			"SELECT 1 FROM information_schema.TABLES"
			" WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s LIMIT 1",
			(table,),
		)
	)


def _column_exists(table, column):
	return bool(
		frappe.db.sql(
			"SELECT 1 FROM information_schema.COLUMNS"
			" WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s"
			" AND COLUMN_NAME = %s LIMIT 1",
			(table, column),
		)
	)


def _missing_live_columns(live, arch):
	live_cols = frappe.db.sql(
		"SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT"
		" FROM information_schema.COLUMNS"
		" WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s"
		" ORDER BY ORDINAL_POSITION",
		(live,),
		as_dict=True,
	)
	arch_cols = {
		r[0]
		for r in frappe.db.sql(
			"SELECT COLUMN_NAME FROM information_schema.COLUMNS"
			" WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
			(arch,),
		)
	}
	out = []
	for c in live_cols:
		if c.COLUMN_NAME in arch_cols:
			continue
		nullable = "NULL" if c.IS_NULLABLE == "YES" else "NULL"
		out.append((c.COLUMN_NAME, f"{c.COLUMN_TYPE} {nullable}"))
	return out


def _ensure_index(table, index_name, columns):
	existing = frappe.db.sql(
		"SELECT 1 FROM information_schema.STATISTICS"
		" WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s"
		" AND INDEX_NAME = %s LIMIT 1",
		(table, index_name),
	)
	if existing:
		return
	cols = ", ".join(f"`{c}`" for c in columns)
	try:
		frappe.db.sql(f"ALTER TABLE `{table}` ADD INDEX `{index_name}` ({cols})")
	except Exception:
		pass


def _date_field_for(doctype):
	for candidate in ("posting_date", "transaction_date", "date", "creation"):
		if frappe.db.has_column(doctype, candidate):
			return candidate
	return None


def _live_columns(table):
	return [
		r[0]
		for r in frappe.db.sql(
			"SELECT COLUMN_NAME FROM information_schema.COLUMNS"
			" WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s"
			" ORDER BY ORDINAL_POSITION",
			(table,),
		)
	]


def _set_run_status(run, status):
	prev = run.status
	allowed = VALID_TRANSITIONS.get(prev, set()) | {status}
	if status not in allowed and prev != status:
		# Allow forced transitions for recovery paths
		pass
	run.status = status
	run.save(ignore_permissions=True)
	frappe.db.commit()


# ---------------------------------------------------------------------------
# Archival run
# ---------------------------------------------------------------------------

def run_archive(run_name=None, confirmation_token=None, skip_preflight=False):
	"""Full Dagaar workflow: validate → snapshot → move → reconcile."""
	ensure_mariadb()
	settings = get_settings()
	if not settings.enabled:
		frappe.throw("Archiving is disabled in Archive Settings.")

	cutoff = getdate(settings.cutoff_date) if settings.cutoff_date else compute_cutoff_date(settings)
	batch_size = cint(settings.batch_size) or 2000
	# Keep one lock token for the whole job — never swap owner mid-run (release would miss).
	lock_owner = frappe.generate_hash(length=12)

	if not preflight.acquire_job_lock(lock_owner):
		frappe.throw("Another archive/restore job holds the exclusive lock.", preflight.PreflightError)

	try:
		with bypass_archives():
			if run_name:
				run = frappe.get_doc("Archive Run", run_name)
			else:
				run = frappe.new_doc("Archive Run")
				run.cutoff_date = cutoff
				run.started_on = now()
				run.schema_version = opening_state.SCHEMA_VERSION
				run.backup_id = getattr(settings, "last_backup_id", None)
				run.backup_checksum = getattr(settings, "last_backup_checksum", None)
				run.insert(ignore_permissions=True)
				frappe.db.commit()

			try:
				_set_run_status(run, "Validating")
				if not skip_preflight:
					report = preflight.run_preflight(
						settings, cutoff, exclude_run=run.name
					)
					run.preflight_report = json.dumps(report, default=str, indent=2)
					run.save(ignore_permissions=True)
					frappe.db.commit()

				_set_run_status(run, "Snapshotting")
				snap = opening_state.build_opening_state(cutoff, run.name)
				run.opening_state_summary = json.dumps(snap, default=str)
				run.save(ignore_permissions=True)
				frappe.db.commit()

				_set_run_status(run, "Moving")
				for rule in get_enabled_rules():
					parent_dt = rule.doctype_name
					# Parents first
					count = _archive_doctype(rule, parent_dt, cutoff, batch_size, run.name, parent_names=None)
					_log_detail(run, parent_dt, count)
					# Children by parent linkage (this run + orphans whose parent is only in archive)
					if rule.archive_children:
						parent_names = _archived_names_for_run(parent_dt, run.name)
						parent_names.extend(_orphan_child_parent_names(rule, parent_dt))
						parent_names = list(dict.fromkeys(parent_names))
						for dt in expanded_rule_doctypes(rule):
							if dt == parent_dt:
								continue
							count = _archive_doctype(
								rule, dt, cutoff, batch_size, run.name, parent_names=parent_names,
								parent_doctype=parent_dt,
							)
							_log_detail(run, dt, count)
					frappe.db.commit()

				_set_run_status(run, "Reconciling")
				compute_snapshots()
				recon = reconcile.run_reconciliation(cutoff, run.name)
				run.reconciliation_report = json.dumps(recon, default=str, indent=2)
				run.save(ignore_permissions=True)
				frappe.db.commit()
				reconcile.assert_reconciliation_passed(recon)

				run.reload()
				run.status = "Completed"
				run.completed_on = now()
				run.save(ignore_permissions=True)
				frappe.db.commit()
				_audit("archive_completed", run.name, {"cutoff": str(cutoff), "recon_ok": True})
			except Exception as exc:
				frappe.db.rollback()
				try:
					# Recover openings so live history + synthetics are not double-counted
					_set_run_status(run, "Recovering")
					opening_state.rebuild_opening_state(cutoff, run.name)
					frappe.db.commit()
				except Exception as recover_exc:
					frappe.log_error(
						f"Opening rebuild after archive failure: {recover_exc}",
						"erpnext_data_archiver",
					)
				run.reload()
				run.status = "Failed"
				run.error = str(exc)[:5000]
				run.save(ignore_permissions=True)
				frappe.db.commit()
				_audit("archive_failed", run.name, {"error": str(exc)[:1000]})
				raise
	finally:
		preflight.release_job_lock(lock_owner)
		clear_metadata_cache()

	return run.name


def _archived_names_for_run(doctype, run_name):
	arch = archive_table_name(doctype)
	if not _table_exists(arch):
		return []
	return [
		r[0]
		for r in frappe.db.sql(
			f"SELECT `name` FROM `{arch}` WHERE `archive_run` = %s",
			(run_name,),
		)
	]


def _orphan_child_parent_names(rule, parent_doctype):
	"""Parents that exist only in archive (prior failed runs left live children)."""
	arch = archive_table_name(parent_doctype)
	live = "tab" + parent_doctype
	if not _table_exists(arch) or not _table_exists(live):
		return []
	return [
		r[0]
		for r in frappe.db.sql(
			f"SELECT a.`name` FROM `{arch}` a"
			f" LEFT JOIN `{live}` l ON l.`name` = a.`name`"
			f" WHERE l.`name` IS NULL"
			f" LIMIT 50000"
		)
	]


def _archive_doctype(rule, doctype, cutoff, batch_size, run_name, parent_names=None, parent_doctype=None):
	"""Copy-verify-delete in batches. Children selected by parent names when provided."""
	live = "tab" + doctype
	if not _table_exists(live):
		return 0

	arch = ensure_archive_table(doctype)
	is_child = parent_names is not None and doctype != rule.doctype_name
	date_field = rule.date_field if rule.doctype_name == doctype else _date_field_for(doctype)

	cols = _live_columns(live)
	# Exclude metadata if somehow present on live
	cols = [c for c in cols if c not in ("archived_on", "archive_run", "fiscal_year_archived")]
	col_sql = ", ".join(f"`{c}`" for c in cols)
	crit_fields = manifest.pick_critical_fields(cols)

	total = 0
	batch_idx = 0

	while True:
		if is_child and parent_names is not None:
			if not parent_names:
				break
			# Process parent_names in chunks
			chunk = parent_names[:batch_size]
			parent_names = parent_names[batch_size:]
			pf = parent_field_for_child(parent_doctype or rule.doctype_name, doctype) or "parent"
			placeholders = ", ".join(["%s"] * len(chunk))
			extra_parenttype = ""
			vals = list(chunk)
			if _column_exists(live, "parenttype"):
				extra_parenttype = " AND `parenttype` = %s"
				vals.append(parent_doctype or rule.doctype_name)
			names = [
				r[0]
				for r in frappe.db.sql(
					f"SELECT `name` FROM `{live}` WHERE `{pf}` IN ({placeholders}){extra_parenttype}",
					vals,
				)
			]
		else:
			if not date_field or not _column_exists(live, date_field):
				return total
			where = [f"`{date_field}` < %s"]
			values = [cutoff]
			# Never re-archive synthetic continuity openings
			if doctype == "GL Entry" and _column_exists(live, "voucher_type"):
				where.append("IFNULL(`voucher_type`, '') != 'Archive Opening'")
			if doctype == "Stock Ledger Entry" and _column_exists(live, "voucher_type"):
				where.append("IFNULL(`voucher_type`, '') != 'Archive Opening'")
			# Never delete into any company's still-open FY (multi-company calendars)
			if _column_exists(live, "company"):
				co_starts = fiscal.company_fy_starts()
				if co_starts:
					parts = []
					vals_extra = []
					for company, start in co_starts.items():
						parts.append(f"(`company` = %s AND `{date_field}` < %s)")
						vals_extra.extend([company, start])
					# Companies without a resolved FY still use global cutoff
					parts.append("(`company` IS NULL OR `company` NOT IN (" + ", ".join(["%s"] * len(co_starts)) + "))")
					vals_extra.extend(list(co_starts.keys()))
					where.append("(" + " OR ".join(parts) + ")")
					values.extend(vals_extra)
			meta = frappe.get_meta(doctype)
			if meta.is_submittable:
				archive_cancelled = cint(getattr(rule, "archive_cancelled", 1))
				if rule.closed_only:
					closed = CLOSED_CONDITIONS.get(doctype) or ""
					# Do not inject free-form closed_condition SQL from settings
					if closed:
						if archive_cancelled:
							where.append(f"(docstatus = 2 OR (docstatus = 1 AND {closed}))")
						else:
							where.append(f"(docstatus = 1 AND {closed})")
				elif not archive_cancelled:
					where.append("docstatus = 1")
			where_sql = " AND ".join(where)
			names = [
				r[0]
				for r in frappe.db.sql(
					f"SELECT `name` FROM `{live}` WHERE {where_sql}"
					f" ORDER BY `{date_field}`, `name` LIMIT %s",
					values + [batch_size],
				)
			]

		if not names:
			if is_child:
				continue
			break

		batch_idx += 1
		# Fingerprints from live before copy
		placeholders = ", ".join(["%s"] * len(names))
		crit_sql = ", ".join(f"`{c}`" for c in crit_fields)
		live_rows = frappe.db.sql(
			f"SELECT {crit_sql} FROM `{live}` WHERE `name` IN ({placeholders})",
			names,
			as_dict=True,
		)
		fps = [manifest.row_fingerprint(r, crit_fields) for r in live_rows]
		expected_hash = manifest.batch_checksum(fps)
		expected_count = len(live_rows)

		fy_subquery = "NULL"
		if date_field and _column_exists(live, date_field):
			fy_subquery = (
				"(SELECT name FROM `tabFiscal Year` fy WHERE `{live}`.`{df}`"
				" BETWEEN fy.year_start_date AND fy.year_end_date"
				" ORDER BY fy.year_start_date DESC LIMIT 1)"
			).format(live=live, df=date_field)

		# When FY master has no match, tag with the year that ended just before cutoff
		# (not str(cutoff)[:4], which wrongly labels Jan-1 cutoffs as the live year).
		day_before = add_days(getdate(cutoff), -1)
		fallback_fy = fiscal.fiscal_year_for_date(day_before) or str(day_before.year)

		frappe.db.sql(
			f"INSERT INTO `{arch}` ({col_sql}, `archived_on`, `archive_run`,"
			f" `fiscal_year_archived`)"
			f" SELECT {col_sql}, NOW(6), %s, {fy_subquery}"
			f" FROM `{live}` WHERE `name` IN ({placeholders})",
			[run_name] + names,
		)
		# Backfill FY when Fiscal Year master had no matching range
		frappe.db.sql(
			f"UPDATE `{arch}` SET `fiscal_year_archived` = COALESCE("
			f"`fiscal_year_archived`, %s) WHERE `archive_run` = %s"
			f" AND `name` IN ({placeholders}) AND (`fiscal_year_archived` IS NULL"
			f" OR `fiscal_year_archived` = '')",
			[fallback_fy] + [run_name] + names,
		)

		arch_rows = frappe.db.sql(
			f"SELECT {crit_sql} FROM `{arch}` WHERE `archive_run` = %s"
			f" AND `name` IN ({placeholders})",
			[run_name] + names,
			as_dict=True,
		)
		actual_fps = [manifest.row_fingerprint(r, crit_fields) for r in arch_rows]
		actual_hash = manifest.batch_checksum(actual_fps)
		actual_count = len(arch_rows)
		try:
			manifest.verify_batch(expected_count, actual_count, expected_hash, actual_hash)
		except ValueError:
			# Do not delete live rows
			frappe.db.rollback()
			_journal_batch(run_name, doctype, batch_idx, expected_count, 0, expected_hash, actual_hash, "Failed")
			raise

		frappe.db.sql(f"DELETE FROM `{live}` WHERE `name` IN ({placeholders})", names)
		_journal_batch(
			run_name, doctype, batch_idx, expected_count, actual_count,
			expected_hash, actual_hash, "Committed",
		)
		frappe.db.commit()
		total += actual_count
		_publish_progress(doctype, total)

		if not is_child and len(names) < batch_size:
			break

	return total


def _journal_batch(run_name, doctype, batch_idx, expected, actual, exp_hash, act_hash, status):
	run = frappe.get_doc("Archive Run", run_name)
	run.append(
		"batches",
		{
			"doctype_name": doctype,
			"batch_index": batch_idx,
			"expected_count": expected,
			"actual_count": actual,
			"expected_checksum": exp_hash,
			"actual_checksum": act_hash,
			"status": status,
		},
	)
	run.save(ignore_permissions=True)


def _log_detail(run, doctype, count):
	if not count:
		return
	run.reload()
	run.append(
		"details",
		{
			"doctype_name": doctype,
			"archive_table": archive_table_name(doctype),
			"rows_archived": count,
		},
	)
	run.save(ignore_permissions=True)

	arch = archive_table_name(doctype)
	for (fy,) in frappe.db.sql(
		f"SELECT DISTINCT `fiscal_year_archived` FROM `{arch}`"
		" WHERE `fiscal_year_archived` IS NOT NULL"
	):
		_register_fiscal_year(fy)


def _register_fiscal_year(fy):
	if not fy or frappe.db.exists("Archived Fiscal Year", fy):
		return
	doc = frappe.new_doc("Archived Fiscal Year")
	doc.fiscal_year = fy
	doc.archived_on = now()
	doc.insert(ignore_permissions=True)


def _publish_progress(doctype, total):
	try:
		frappe.publish_realtime(
			"eda_archive_progress",
			{"doctype": doctype, "rows_archived": total},
		)
	except Exception:
		pass


def _audit(action, scope, detail=None):
	try:
		if not frappe.db.exists("DocType", "Archive Audit Log"):
			return
		doc = frappe.get_doc(
			{
				"doctype": "Archive Audit Log",
				"action": action,
				"scope": scope,
				"actor": getattr(frappe.session, "user", None) or "Administrator",
				"detail": json.dumps(detail or {}, default=str),
				"timestamp": now_datetime(),
			}
		)
		doc.insert(ignore_permissions=True)
		frappe.db.commit()
	except Exception:
		pass


# ---------------------------------------------------------------------------
# Snapshots (audit aggregates)
# ---------------------------------------------------------------------------

def compute_snapshots():
	with bypass_archives():
		_compute_gl_snapshots()
		_compute_stock_snapshots()


def _fy_sort_key(fy_name):
	"""Chronological sort for fiscal year labels (not lexicographic)."""
	start, end = fiscal.fiscal_year_bounds(fy_name)
	if start:
		return (getdate(start), str(fy_name))
	inferred = fiscal._infer_year_end(fy_name)
	if inferred:
		return (getdate(inferred), str(fy_name))
	return (getdate("9999-12-31"), str(fy_name))


def _compute_gl_snapshots():
	arch = archive_table_name("GL Entry")
	if not _table_exists(arch):
		return
	rows = frappe.db.sql(
		f"SELECT `fiscal_year_archived`, `company`, `account`,"
		f" SUM(`debit`), SUM(`credit`) FROM `{arch}`"
		" WHERE `fiscal_year_archived` IS NOT NULL"
		" GROUP BY `fiscal_year_archived`, `company`, `account`",
	)
	if not rows:
		return

	years = sorted({r[0] for r in rows}, key=_fy_sort_key)
	cumulative = {}
	frappe.db.sql("DELETE FROM `tabArchived GL Balance`")
	for year in years:
		for fy, company, account, debit, credit in [r for r in rows if r[0] == year]:
			key = (company, account)
			bal = cumulative.get(key, 0.0) + (float(debit or 0) - float(credit or 0))
			cumulative[key] = bal
			frappe.db.sql(
				"INSERT INTO `tabArchived GL Balance`"
				" (`name`, `creation`, `modified`, `modified_by`, `owner`,"
				"  `docstatus`, `idx`, `fiscal_year`, `company`, `account`,"
				"  `debit`, `credit`, `balance`)"
				" VALUES (%s, %s, %s, 'Administrator', 'Administrator', 0, 0,"
				"         %s, %s, %s, %s, %s, %s)",
				(
					frappe.generate_hash(length=10),
					now_datetime(),
					now_datetime(),
					year,
					company,
					account,
					float(debit or 0),
					float(credit or 0),
					bal,
				),
			)
	frappe.db.commit()


def _compute_stock_snapshots():
	arch = archive_table_name("Stock Ledger Entry")
	if not _table_exists(arch) or not _column_exists(arch, "item_code"):
		return
	rows = frappe.db.sql(
		f"SELECT `fiscal_year_archived`, `item_code`, `warehouse`,"
		f" SUM(`actual_qty`), SUM(`stock_value_difference`) FROM `{arch}`"
		" WHERE `fiscal_year_archived` IS NOT NULL AND `is_cancelled` = 0"
		" GROUP BY `fiscal_year_archived`, `item_code`, `warehouse`"
		if _column_exists(arch, "is_cancelled")
		else f"SELECT `fiscal_year_archived`, `item_code`, `warehouse`,"
		f" SUM(`actual_qty`), SUM(`stock_value_difference`) FROM `{arch}`"
		" WHERE `fiscal_year_archived` IS NOT NULL"
		" GROUP BY `fiscal_year_archived`, `item_code`, `warehouse`",
	)
	if not rows:
		return

	years = sorted({r[0] for r in rows}, key=_fy_sort_key)
	cumulative = {}
	frappe.db.sql("DELETE FROM `tabArchived Stock Balance`")
	for year in years:
		for fy, item, warehouse, qty, value in [r for r in rows if r[0] == year]:
			key = (item, warehouse)
			qty_cum = cumulative.get(key, (0.0, 0.0))[0] + float(qty or 0)
			val_cum = cumulative.get(key, (0.0, 0.0))[1] + float(value or 0)
			cumulative[key] = (qty_cum, val_cum)
			rate = (val_cum / qty_cum) if qty_cum else 0.0
			frappe.db.sql(
				"INSERT INTO `tabArchived Stock Balance`"
				" (`name`, `creation`, `modified`, `modified_by`, `owner`,"
				"  `docstatus`, `idx`, `fiscal_year`, `item_code`, `warehouse`,"
				"  `qty`, `valuation_rate`, `stock_value`)"
				" VALUES (%s, %s, %s, 'Administrator', 'Administrator', 0, 0,"
				"         %s, %s, %s, %s, %s, %s)",
				(
					frappe.generate_hash(length=10),
					now_datetime(),
					now_datetime(),
					year,
					item,
					warehouse,
					qty_cum,
					rate,
					val_cum,
				),
			)
	frappe.db.commit()


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------

def preview_restore(fiscal_year) -> dict:
	"""Dry-run collision report for restore."""
	ensure_mariadb()
	collisions = []
	totals = []
	with bypass_archives():
		for rule in get_enabled_rules():
			for dt in expanded_rule_doctypes(rule):
				live = "tab" + dt
				arch = archive_table_name(dt)
				if not _table_exists(live) or not _table_exists(arch):
					continue
				count = cint(
					frappe.db.sql(
						f"SELECT COUNT(*) FROM `{arch}` WHERE `fiscal_year_archived` = %s",
						(fiscal_year,),
					)[0][0]
				)
				if not count:
					continue
				hit = frappe.db.sql(
					f"SELECT a.`name` FROM `{arch}` a INNER JOIN `{live}` l"
					f" ON a.`name` = l.`name`"
					f" WHERE a.`fiscal_year_archived` = %s LIMIT 50",
					(fiscal_year,),
				)
				names = [r[0] for r in hit]
				totals.append({"doctype": dt, "rows": count, "collisions": len(names)})
				if names:
					collisions.append({"doctype": dt, "names": names})
	return {
		"fiscal_year": fiscal_year,
		"ok": not collisions,
		"collisions": collisions,
		"doctypes": totals,
	}


def restore_fiscal_year(fiscal_year, force=False):
	"""Copy one archived fiscal year back into live tables (no silent overwrite)."""
	ensure_mariadb()
	lock_owner = f"restore:{fiscal_year}"
	if not preflight.acquire_job_lock(lock_owner):
		frappe.throw("Another archive/restore job holds the exclusive lock.")

	try:
		preview = preview_restore(fiscal_year)
		if not preview["ok"] and not force:
			frappe.throw(
				"Restore blocked: primary key collisions in live tables. "
				"Resolve collisions or pass force=1 after review. "
				+ json.dumps(preview["collisions"][:5], default=str)
			)

		with bypass_archives():
			for rule in get_enabled_rules():
				# Children first? Parents first then children for insert; parents first is fine
				# if children reference parent by name without FK enforcement.
				for dt in expanded_rule_doctypes(rule):
					_restore_doctype(dt, fiscal_year, allow_ignore=force)
					frappe.db.commit()

			# Drop openings keyed to this FY end+1, then rebuild for the live cutoff
			_clear_openings_for_fiscal_year(fiscal_year)
			live_cutoff = get_archive_cutoff()
			opening_state.rebuild_opening_state(live_cutoff, archive_run=f"restore:{fiscal_year}")

			if frappe.db.exists("Archived Fiscal Year", fiscal_year):
				frappe.delete_doc("Archived Fiscal Year", fiscal_year, ignore_permissions=True)
			frappe.db.commit()
			_audit("restore_completed", fiscal_year, preview)
	finally:
		preflight.release_job_lock(lock_owner)
		clear_metadata_cache()


def _clear_openings_for_fiscal_year(fiscal_year):
	"""Clear openings that belong to this FY and any openings at the live cutoff.

	Openings are usually keyed to the archive-run cutoff (current FY start), not
	year_end+1. Clear both so restore does not leave stale synthetics.
	"""
	from frappe.utils import add_days

	row = frappe.db.get_value(
		"Fiscal Year", fiscal_year, ["year_end_date", "year_start_date"], as_dict=True
	)
	cutoffs = {get_archive_cutoff()}
	if row and row.year_end_date:
		cutoffs.add(add_days(getdate(row.year_end_date), 1))
	inferred = fiscal._infer_year_end(fiscal_year)
	if inferred:
		cutoffs.add(add_days(getdate(inferred), 1))
	for cutoff in cutoffs:
		if cutoff:
			opening_state.clear_opening_state_for_cutoff(cutoff)


def _restore_doctype(doctype, fiscal_year, allow_ignore=False):
	live = "tab" + doctype
	arch = archive_table_name(doctype)
	if not _table_exists(live) or not _table_exists(arch):
		return
	cols = _live_columns(live)
	cols = [c for c in cols if c not in ("archived_on", "archive_run", "fiscal_year_archived")]
	col_sql = ", ".join(f"`{c}`" for c in cols)
	verb = "INSERT IGNORE" if allow_ignore else "INSERT"
	frappe.db.sql(
		f"{verb} INTO `{live}` ({col_sql})"
		f" SELECT {col_sql} FROM `{arch}` WHERE `fiscal_year_archived` = %s",
		(fiscal_year,),
	)
	if allow_ignore:
		# Only remove archive rows that actually landed in live (collisions stay archived).
		frappe.db.sql(
			f"DELETE `a` FROM `{arch}` `a`"
			f" INNER JOIN `{live}` `l` ON `l`.`name` = `a`.`name`"
			f" WHERE `a`.`fiscal_year_archived` = %s",
			(fiscal_year,),
		)
	else:
		frappe.db.sql(
			f"DELETE FROM `{arch}` WHERE `fiscal_year_archived` = %s",
			(fiscal_year,),
		)


# ---------------------------------------------------------------------------
# Reporting helpers for the UI
# ---------------------------------------------------------------------------

def get_archived_year_stats():
	stats = {}
	with bypass_archives():
		for rule in get_enabled_rules():
			for dt in expanded_rule_doctypes(rule):
				arch = archive_table_name(dt)
				if not _table_exists(arch):
					continue
				for fy, count in frappe.db.sql(
					f"SELECT `fiscal_year_archived`, COUNT(*) FROM `{arch}`"
					" WHERE `fiscal_year_archived` IS NOT NULL"
					" GROUP BY `fiscal_year_archived`"
				):
					stats.setdefault(fy, 0)
					stats[fy] += cint(count)
	return [{"fiscal_year": fy, "rows": rows} for fy, rows in sorted(stats.items())]


def get_archivable_years():
	"""Completed fiscal years operators can choose to archive through.

	Includes Fiscal Year master rows, already-archived years, and a
	calendar fallback so sparse FY masters still offer a clear choice.
	"""
	from frappe.utils import add_days

	from erpnext_data_archiver.archiver import fiscal

	current_start = getdate(fiscal.current_fy_start())
	archived = {y["fiscal_year"]: y["rows"] for y in get_archived_year_stats()}
	by_name = {}

	def _add(fy, start, end, inferred=False):
		end = getdate(end)
		if end >= current_start:
			return
		start = getdate(start) if start else None
		cutoff = add_days(end, 1)
		by_name[fy] = {
			"fiscal_year": fy,
			"year_start": str(start) if start else None,
			"year_end": str(end),
			"cutoff_date": str(cutoff),
			"already_archived": fy in archived,
			"archived_rows": archived.get(fy, 0),
			"inferred": inferred,
		}

	for row in fiscal.list_completed_fiscal_years():
		_add(row.name, row.year_start_date, row.year_end_date)

	extra_names = set(archived)
	if frappe.db.exists("DocType", "Archived Fiscal Year"):
		extra_names.update(frappe.get_all("Archived Fiscal Year", pluck="name") or [])

	for fy in extra_names:
		if fy in by_name:
			continue
		start, end = fiscal.fiscal_year_bounds(fy)
		if not end:
			end = fiscal._infer_year_end(fy)
			start = getdate(f"{getdate(end).year}-01-01") if end else None
			_add(fy, start, end, inferred=True)
		else:
			_add(fy, start, end)

	# Always offer the calendar year just before the live FY start when missing
	prev = current_start.year - 1
	prev_name = str(prev)
	if prev_name not in by_name:
		_add(prev_name, getdate(f"{prev}-01-01"), getdate(f"{prev}-12-31"), inferred=True)

	return [by_name[k] for k in sorted(by_name.keys())]


def apply_archive_through_year(fiscal_year, settings=None):
	"""Persist year + derived cutoff on Archive Settings; return cutoff date."""
	from erpnext_data_archiver.archiver import fiscal

	if not fiscal_year:
		frappe.throw("Pick a fiscal year to archive through.")
	cutoff = fiscal.cutoff_after_fiscal_year(fiscal_year)
	live_start = fiscal.current_fy_start()
	if getdate(cutoff) > getdate(live_start):
		frappe.throw(
			f"Cannot archive through {fiscal_year}: that would touch the current fiscal year."
		)

	settings = settings or get_settings()
	frappe.db.set_value(
		"Archive Settings",
		None,
		{
			"archive_through_year": fiscal_year,
			"cutoff_date": cutoff,
		},
		update_modified=False,
	)
	# Keep in-memory doc in sync for this request
	settings.archive_through_year = fiscal_year
	settings.cutoff_date = cutoff
	return cutoff


def get_live_table_stats():
	stats = []
	with bypass_archives():
		for rule in get_enabled_rules():
			dt = rule.doctype_name
			live = "tab" + dt
			if not _table_exists(live):
				continue
			count = frappe.db.sql(f"SELECT COUNT(*) FROM `{live}`")[0][0]
			stats.append({"doctype": dt, "live_rows": cint(count)})
	return stats


def get_archive_cutoff():
	settings = get_settings()
	if settings.cutoff_date:
		return getdate(settings.cutoff_date)
	return getdate(compute_cutoff_date(settings))
