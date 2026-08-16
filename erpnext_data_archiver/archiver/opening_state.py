"""Opening-state snapshots for hot-path continuity after archival.

Built from live ledgers **before** rows are deleted. Active-period reports use
synthetic live GL / SLE opening rows (and compact DocType mirrors) instead of
scanning archive tables.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import frappe
from frappe.utils import add_days, cint, flt, getdate

OPENING_DOCTYPES = (
	"Archive Opening GL",
	"Archive Opening Party",
	"Archive Opening Stock",
	"Archive Opening Stock Queue",
)

SCHEMA_VERSION = "1.0.0"
SYNTH_VOUCHER = "Archive Opening"


def make_idempotency_key(*parts: Any) -> str:
	"""Deterministic unique key for synthetic opening rows (ACC-006 / STK)."""
	raw = "|".join("" if p is None else str(p) for p in parts)
	return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def build_opening_state(cutoff, archive_run: str | None = None) -> dict:
	"""Compute and persist all opening-state layers for ``cutoff``."""
	from erpnext_data_archiver.archiver.query_patch import bypass_archives

	cutoff = getdate(cutoff)
	with bypass_archives():
		gl = _build_gl_openings(cutoff, archive_run)
		party = _build_party_openings(cutoff, archive_run)
		stock = _build_stock_openings(cutoff, archive_run)
		queue = _build_stock_queue(cutoff, archive_run)
		frappe.db.commit()
	return {
		"gl_rows": gl,
		"party_rows": party,
		"stock_rows": stock,
		"queue_rows": queue,
		"schema_version": SCHEMA_VERSION,
	}


def rebuild_opening_state(cutoff, archive_run: str | None = None) -> dict:
	"""Force rebuild from whatever live history remains (failure / restore)."""
	return build_opening_state(cutoff, archive_run)


def clear_opening_state_for_cutoff(cutoff) -> None:
	"""Remove synthetic openings for a cutoff (e.g. after full FY restore)."""
	from erpnext_data_archiver.archiver.query_patch import bypass_archives

	cutoff = getdate(cutoff)
	with bypass_archives():
		_clear_synthetic_gl_entries()
		_clear_synthetic_sle_entries()
		for dt in OPENING_DOCTYPES:
			if not frappe.db.exists("DocType", dt):
				continue
			frappe.db.delete(dt, {"cutoff_date": cutoff})
		frappe.db.commit()


def clear_opening_state_for_run(archive_run: str) -> None:
	from erpnext_data_archiver.archiver.query_patch import bypass_archives

	with bypass_archives():
		_clear_synthetic_gl_entries()
		_clear_synthetic_sle_entries()
		for dt in OPENING_DOCTYPES:
			if not frappe.db.exists("DocType", dt):
				continue
			frappe.db.delete(dt, {"archive_run": archive_run})
		frappe.db.commit()


def _upsert(doctype: str, key: str, values: dict) -> None:
	existing = frappe.db.get_value(doctype, {"idempotency_key": key}, "name")
	if existing:
		doc = frappe.get_doc(doctype, existing)
		doc.update(values)
		doc.idempotency_key = key
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc({"doctype": doctype, "idempotency_key": key, **values})
		doc.insert(ignore_permissions=True)


def _column_exists(table: str, column: str) -> bool:
	return bool(
		frappe.db.sql(
			"SELECT 1 FROM information_schema.COLUMNS"
			" WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s"
			" AND COLUMN_NAME = %s LIMIT 1",
			(table, column),
		)
	)


def _build_gl_openings(cutoff, archive_run) -> int:
	if not frappe.db.table_exists("GL Entry"):
		return 0

	is_cancelled = ""
	if _column_exists("tabGL Entry", "is_cancelled"):
		is_cancelled = " AND IFNULL(`is_cancelled`, 0) = 0"

	exclude_synth = ""
	if _column_exists("tabGL Entry", "voucher_type"):
		exclude_synth = f" AND IFNULL(`voucher_type`, '') != '{SYNTH_VOUCHER}'"

	live_hist = frappe.db.sql(
		f"""
		SELECT COUNT(*) FROM `tabGL Entry`
		WHERE `posting_date` < %s {is_cancelled}{exclude_synth}
		""",
		(cutoff,),
	)[0][0]
	existing = frappe.db.count("Archive Opening GL", {"cutoff_date": cutoff})
	if cint(live_hist) == 0 and cint(existing) > 0:
		return cint(existing)

	_clear_synthetic_gl_entries()

	dims = []
	for col in ("cost_center", "project", "finance_book"):
		if _column_exists("tabGL Entry", col):
			dims.append(col)

	dim_select = "".join(f", `{c}`" for c in dims)
	dim_group = (", " + ", ".join(f"`{c}`" for c in dims)) if dims else ""

	rows = frappe.db.sql(
		f"""
		SELECT `company`, `account`{dim_select},
			SUM(`debit`), SUM(`credit`)
		FROM `tabGL Entry`
		WHERE `posting_date` < %s {is_cancelled}{exclude_synth}
		GROUP BY `company`, `account`{dim_group}
		""",
		(cutoff,),
	)

	count = 0
	posting = add_days(getdate(cutoff), -1)
	for row in rows:
		company, account = row[0], row[1]
		extra = row[2 : 2 + len(dims)]
		debit = flt(row[2 + len(dims)])
		credit = flt(row[3 + len(dims)])
		if not debit and not credit:
			continue
		cc = extra[0] if len(dims) > 0 else None
		project = extra[1] if len(dims) > 1 else None
		fb = extra[2] if len(dims) > 2 else None
		key = make_idempotency_key("gl", cutoff, company, account, cc, project, fb)
		_upsert(
			"Archive Opening GL",
			key,
			{
				"cutoff_date": cutoff,
				"company": company,
				"account": account,
				"cost_center": cc,
				"project": project,
				"finance_book": fb,
				"debit": debit,
				"credit": credit,
				"balance": debit - credit,
				"is_synthetic": 1,
				"archive_run": archive_run,
			},
		)
		_insert_synthetic_gl(
			name_key=key,
			company=company,
			account=account,
			debit=debit,
			credit=credit,
			posting_date=posting,
			cost_center=cc,
			project=project,
			finance_book=fb,
			archive_run=archive_run,
		)
		count += 1
	return count


def _clear_synthetic_gl_entries() -> None:
	if not frappe.db.table_exists("GL Entry"):
		return
	if not _column_exists("tabGL Entry", "voucher_type"):
		return
	frappe.db.sql(
		"DELETE FROM `tabGL Entry` WHERE `voucher_type` = %s",
		(SYNTH_VOUCHER,),
	)


def _clear_synthetic_sle_entries() -> None:
	if not frappe.db.table_exists("Stock Ledger Entry"):
		return
	if not _column_exists("tabStock Ledger Entry", "voucher_type"):
		return
	frappe.db.sql(
		"DELETE FROM `tabStock Ledger Entry` WHERE `voucher_type` = %s",
		(SYNTH_VOUCHER,),
	)


def _insert_synthetic_gl(
	name_key,
	company,
	account,
	debit,
	credit,
	posting_date,
	cost_center=None,
	project=None,
	finance_book=None,
	archive_run=None,
):
	"""Compact live GL rows so active reports need no archive scans (ARCH-001)."""
	name = ("EDA-OPEN-" + name_key)[:140]
	if frappe.db.exists("GL Entry", name):
		frappe.db.sql("DELETE FROM `tabGL Entry` WHERE `name` = %s", (name,))

	now = frappe.utils.now_datetime() if hasattr(frappe.utils, "now_datetime") else posting_date
	fields = {
		"name": name,
		"creation": now,
		"modified": now,
		"modified_by": "Administrator",
		"owner": "Administrator",
		"docstatus": 1,
		"idx": 0,
		"posting_date": posting_date,
		"account": account,
		"company": company,
		"debit": debit,
		"credit": credit,
		"voucher_type": SYNTH_VOUCHER,
		"voucher_no": archive_run or name,
		"remarks": "Synthetic opening for archived period (erpnext_data_archiver)",
		"is_opening": "Yes" if _column_exists("tabGL Entry", "is_opening") else None,
	}
	if cost_center and _column_exists("tabGL Entry", "cost_center"):
		fields["cost_center"] = cost_center
	if project and _column_exists("tabGL Entry", "project"):
		fields["project"] = project
	if finance_book and _column_exists("tabGL Entry", "finance_book"):
		fields["finance_book"] = finance_book
	if _column_exists("tabGL Entry", "is_cancelled"):
		fields["is_cancelled"] = 0

	fields = {k: v for k, v in fields.items() if v is not None}
	cols = ", ".join(f"`{c}`" for c in fields)
	placeholders = ", ".join(["%s"] * len(fields))
	frappe.db.sql(
		f"INSERT INTO `tabGL Entry` ({cols}) VALUES ({placeholders})",
		list(fields.values()),
	)


def _build_party_openings(cutoff, archive_run) -> int:
	"""Retain unpaid invoice-level identity for aging continuity."""
	count = 0
	existing = frappe.db.count("Archive Opening Party", {"cutoff_date": cutoff}) if frappe.db.exists(
		"DocType", "Archive Opening Party"
	) else 0
	live_unpaid = 0
	for doctype, party_type, party_field, account_field in (
		("Sales Invoice", "Customer", "customer", "debit_to"),
		("Purchase Invoice", "Supplier", "supplier", "credit_to"),
	):
		if not frappe.db.table_exists(doctype):
			continue
		has_account = _column_exists(f"tab{doctype}", account_field)
		account_sel = f"`{account_field}`" if has_account else "NULL"
		rows = frappe.db.sql(
			f"""
			SELECT `name`, `company`, `{party_field}`, `outstanding_amount`,
				`due_date`, {account_sel}
			FROM `tab{doctype}`
			WHERE `docstatus` = 1
				AND IFNULL(`outstanding_amount`, 0) != 0
				AND `posting_date` < %s
			""",
			(cutoff,),
		)
		live_unpaid += len(rows)
		for name, company, party, outstanding, due_date, account in rows:
			key = make_idempotency_key("party", cutoff, doctype, name)
			_upsert(
				"Archive Opening Party",
				key,
				{
					"cutoff_date": cutoff,
					"company": company,
					"party_type": party_type,
					"party": party,
					"voucher_type": doctype,
					"voucher_no": name,
					"against_voucher_type": doctype,
					"against_voucher": name,
					"account": account,
					"due_date": due_date,
					"outstanding": flt(outstanding),
					"is_synthetic": 1,
					"archive_run": archive_run,
				},
			)
			count += 1
	if live_unpaid == 0 and existing > 0 and count == 0:
		return cint(existing)
	return count


def _build_stock_openings(cutoff, archive_run) -> int:
	if not frappe.db.table_exists("Stock Ledger Entry"):
		return 0

	cancelled = ""
	if _column_exists("tabStock Ledger Entry", "is_cancelled"):
		cancelled = " AND IFNULL(`is_cancelled`, 0) = 0"
	exclude_synth = ""
	if _column_exists("tabStock Ledger Entry", "voucher_type"):
		exclude_synth = f" AND IFNULL(`voucher_type`, '') != '{SYNTH_VOUCHER}'"

	live_hist = frappe.db.sql(
		f"""
		SELECT COUNT(*) FROM `tabStock Ledger Entry`
		WHERE `posting_date` < %s {cancelled}{exclude_synth}
		""",
		(cutoff,),
	)[0][0]
	existing = frappe.db.count("Archive Opening Stock", {"cutoff_date": cutoff})
	if cint(live_hist) == 0 and cint(existing) > 0:
		return cint(existing)

	_clear_synthetic_sle_entries()

	company_sel = ", `company`" if _column_exists("tabStock Ledger Entry", "company") else ", NULL"
	company_grp = ", `company`" if _column_exists("tabStock Ledger Entry", "company") else ""

	rows = frappe.db.sql(
		f"""
		SELECT `item_code`, `warehouse`{company_sel},
			SUM(`actual_qty`), SUM(`stock_value_difference`)
		FROM `tabStock Ledger Entry`
		WHERE `posting_date` < %s {cancelled}{exclude_synth}
		GROUP BY `item_code`, `warehouse`{company_grp}
		""",
		(cutoff,),
	)
	count = 0
	posting = add_days(getdate(cutoff), -1)
	for row in rows:
		item, warehouse, company, qty, value = row[0], row[1], row[2], flt(row[3]), flt(row[4])
		if not qty and not value:
			continue
		rate = (value / qty) if qty else 0.0
		key = make_idempotency_key("stock", cutoff, item, warehouse, company)
		_upsert(
			"Archive Opening Stock",
			key,
			{
				"cutoff_date": cutoff,
				"item_code": item,
				"warehouse": warehouse,
				"qty": qty,
				"stock_value": value,
				"valuation_rate": rate,
				"is_synthetic": 1,
				"archive_run": archive_run,
			},
		)
		_insert_synthetic_sle(
			name_key=key,
			item_code=item,
			warehouse=warehouse,
			company=company,
			qty=qty,
			value=value,
			rate=rate,
			posting_date=posting,
			archive_run=archive_run,
		)
		count += 1
	return count


def _insert_synthetic_sle(
	name_key,
	item_code,
	warehouse,
	company,
	qty,
	value,
	rate,
	posting_date,
	archive_run=None,
):
	"""Compact live SLE so Stock Balance / Ledger hot paths stay archive-free."""
	name = ("EDA-SLE-" + name_key)[:140]
	if frappe.db.exists("Stock Ledger Entry", name):
		frappe.db.sql("DELETE FROM `tabStock Ledger Entry` WHERE `name` = %s", (name,))

	now = frappe.utils.now_datetime() if hasattr(frappe.utils, "now_datetime") else posting_date
	fields = {
		"name": name,
		"creation": now,
		"modified": now,
		"modified_by": "Administrator",
		"owner": "Administrator",
		"docstatus": 1,
		"idx": 0,
		"item_code": item_code,
		"warehouse": warehouse,
		"posting_date": posting_date,
		"actual_qty": qty,
		"qty_after_transaction": qty,
		"stock_value_difference": value,
		"stock_value": value,
		"valuation_rate": rate,
		"voucher_type": SYNTH_VOUCHER,
		"voucher_no": archive_run or name,
	}
	if company and _column_exists("tabStock Ledger Entry", "company"):
		fields["company"] = company
	if _column_exists("tabStock Ledger Entry", "posting_time"):
		fields["posting_time"] = "23:59:59"
	if _column_exists("tabStock Ledger Entry", "is_cancelled"):
		fields["is_cancelled"] = 0
	if _column_exists("tabStock Ledger Entry", "is_opening"):
		fields["is_opening"] = "Yes"

	fields = {k: v for k, v in fields.items() if v is not None}
	cols = ", ".join(f"`{c}`" for c in fields)
	placeholders = ", ".join(["%s"] * len(fields))
	frappe.db.sql(
		f"INSERT INTO `tabStock Ledger Entry` ({cols}) VALUES ({placeholders})",
		list(fields.values()),
	)


def _build_stock_queue(cutoff, archive_run) -> int:
	"""Reconstruct FIFO layers as-of cutoff from SLE (consume outgoings)."""
	if not frappe.db.table_exists("Stock Ledger Entry"):
		return 0

	existing = frappe.db.count("Archive Opening Stock Queue", {"cutoff_date": cutoff})
	cancelled = ""
	if _column_exists("tabStock Ledger Entry", "is_cancelled"):
		cancelled = " AND IFNULL(`is_cancelled`, 0) = 0"
	exclude_synth = ""
	if _column_exists("tabStock Ledger Entry", "voucher_type"):
		exclude_synth = f" AND IFNULL(`voucher_type`, '') != '{SYNTH_VOUCHER}'"

	live_hist = frappe.db.sql(
		f"""
		SELECT COUNT(*) FROM `tabStock Ledger Entry`
		WHERE `posting_date` < %s {cancelled}{exclude_synth}
		""",
		(cutoff,),
	)[0][0]
	if cint(live_hist) == 0 and cint(existing) > 0:
		return cint(existing)

	# Clear prior queue rows for this cutoff then rebuild
	if frappe.db.exists("DocType", "Archive Opening Stock Queue"):
		frappe.db.delete("Archive Opening Stock Queue", {"cutoff_date": cutoff})

	rate_col = "incoming_rate" if _column_exists("tabStock Ledger Entry", "incoming_rate") else "valuation_rate"
	order = "`posting_date`, `posting_time`, `creation`"
	if not _column_exists("tabStock Ledger Entry", "posting_time"):
		order = "`posting_date`, `creation`"

	rows = frappe.db.sql(
		f"""
		SELECT `item_code`, `warehouse`, `actual_qty`, IFNULL(`{rate_col}`, 0),
			`posting_date`, `voucher_type`, `voucher_no`
		FROM `tabStock Ledger Entry`
		WHERE `posting_date` < %s {cancelled}{exclude_synth}
		ORDER BY `item_code`, `warehouse`, {order}
		""",
		(cutoff,),
	)

	# item, warehouse -> list of [qty, rate]
	queues: dict[tuple, list] = {}
	meta: dict[tuple, tuple] = {}
	for item, warehouse, qty, rate, posting_date, vt, vn in rows:
		k = (item, warehouse)
		layers = queues.setdefault(k, [])
		qty = flt(qty)
		rate = flt(rate)
		if qty > 0:
			layers.append([qty, rate])
			meta[k] = (posting_date, vt, vn)
		elif qty < 0:
			need = -qty
			while need > 0 and layers:
				lq, lr = layers[0]
				if lq <= need + 1e-9:
					need -= lq
					layers.pop(0)
				else:
					layers[0][0] = lq - need
					need = 0

	count = 0
	for (item, warehouse), layers in queues.items():
		posting_date, vt, vn = meta.get((item, warehouse), (None, None, None))
		for idx, layer in enumerate(layers):
			lq, lr = flt(layer[0]), flt(layer[1])
			if abs(lq) < 1e-9:
				continue
			key = make_idempotency_key("queue", cutoff, item, warehouse, idx)
			_upsert(
				"Archive Opening Stock Queue",
				key,
				{
					"cutoff_date": cutoff,
					"item_code": item,
					"warehouse": warehouse,
					"queue_index": idx,
					"qty": lq,
					"valuation_rate": lr,
					"stock_value": lq * lr,
					"posting_date": posting_date,
					"voucher_type": vt,
					"voucher_no": vn,
					"is_synthetic": 1,
					"archive_run": archive_run,
				},
			)
			count += 1
	return count
