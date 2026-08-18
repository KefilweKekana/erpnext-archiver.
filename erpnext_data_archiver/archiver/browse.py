"""Browse archived documents by DocType for selected fiscal years."""

from __future__ import annotations

import frappe
from frappe.utils import cint

from erpnext_data_archiver.archiver.engine import get_enabled_rules
from erpnext_data_archiver.archiver.query_patch import archive_table_name, bypass_archives

DISPLAY_COLS = (
	"name",
	"posting_date",
	"transaction_date",
	"customer",
	"customer_name",
	"supplier",
	"supplier_name",
	"account",
	"party",
	"party_type",
	"item_code",
	"warehouse",
	"voucher_type",
	"voucher_no",
	"grand_total",
	"debit",
	"credit",
	"status",
	"fiscal_year_archived",
)


def _table_exists(table: str) -> bool:
	return bool(
		frappe.db.sql(
			"SELECT 1 FROM information_schema.TABLES"
			" WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s LIMIT 1",
			(table,),
		)
	)


def _has_col(table: str, column: str) -> bool:
	return bool(
		frappe.db.sql(
			"SELECT 1 FROM information_schema.COLUMNS"
			" WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s LIMIT 1",
			(table, column),
		)
	)


def _columns(table: str) -> set[str]:
	rows = frappe.db.sql(
		"SELECT COLUMN_NAME FROM information_schema.COLUMNS"
		" WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
		(table,),
	)
	return {r[0] for r in rows}


def _parse_years(years) -> list[str]:
	if years is None or years == "":
		return []
	if isinstance(years, str):
		import json

		s = years.strip()
		if s.startswith("["):
			try:
				years = json.loads(s)
			except Exception:
				years = [s]
		elif "," in s:
			years = [p.strip() for p in s.split(",") if p.strip()]
		else:
			years = [s]
	elif not isinstance(years, (list, tuple)):
		years = [years]
	return [str(y).strip() for y in years if str(y).strip()]


def _parent_doctypes() -> list[str]:
	names = []
	for rule in get_enabled_rules():
		if rule.doctype_name:
			names.append(rule.doctype_name)
	return list(dict.fromkeys(names))


def list_doctypes(years) -> list[dict]:
	"""DocTypes that have rows in archive for the selected years."""
	years = _parse_years(years)
	if not years:
		return []
	placeholders = ", ".join(["%s"] * len(years))
	out = []
	with bypass_archives():
		for dt in _parent_doctypes():
			arch = archive_table_name(dt)
			if not _table_exists(arch) or not _has_col(arch, "fiscal_year_archived"):
				continue
			count = cint(
				frappe.db.sql(
					f"SELECT COUNT(*) FROM `{arch}` WHERE `fiscal_year_archived` IN ({placeholders})",
					years,
				)[0][0]
			)
			if count:
				out.append({"doctype": dt, "rows": count})
	out.sort(key=lambda r: (-r["rows"], r["doctype"]))
	return out


def list_documents(doctype: str, years, start=0, page_length=25, search=""):
	"""One page of archived documents for a DocType and years."""
	doctype = (doctype or "").strip()
	if doctype not in _parent_doctypes():
		frappe.throw("That DocType is not archived on this site.")
	years = _parse_years(years)
	if not years:
		frappe.throw("Tick an archived year first.")

	arch = archive_table_name(doctype)
	if not _table_exists(arch):
		return {"doctype": doctype, "rows": [], "total": 0, "start": 0, "has_more": False}

	present = _columns(arch)
	if "fiscal_year_archived" not in present:
		return {"doctype": doctype, "rows": [], "total": 0, "start": 0, "has_more": False}

	start = max(0, cint(start))
	page_length = max(1, min(cint(page_length) or 25, 50))
	search = (search or "").strip()

	cols = [c for c in DISPLAY_COLS if c in present]
	if "name" not in cols:
		cols.insert(0, "name")
	select = ", ".join(f"`{c}`" for c in cols)
	placeholders = ", ".join(["%s"] * len(years))
	where = [f"`fiscal_year_archived` IN ({placeholders})"]
	values = list(years)
	if search:
		like = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
		ors = ["`name` LIKE %s"]
		values.append(like)
		for extra in ("customer", "customer_name", "supplier", "supplier_name", "account", "voucher_no", "item_code"):
			if extra in cols:
				ors.append(f"`{extra}` LIKE %s")
				values.append(like)
		where.append("(" + " OR ".join(ors) + ")")
	where_sql = " AND ".join(where)
	if "posting_date" in cols:
		order = "`posting_date` DESC, `name` DESC"
	elif "transaction_date" in cols:
		order = "`transaction_date` DESC, `name` DESC"
	else:
		order = "`name` DESC"

	with bypass_archives():
		total = cint(
			frappe.db.sql(f"SELECT COUNT(*) FROM `{arch}` WHERE {where_sql}", values)[0][0]
		)
		rows = frappe.db.sql(
			f"SELECT {select} FROM `{arch}` WHERE {where_sql}"
			f" ORDER BY {order} LIMIT %s OFFSET %s",
			values + [page_length, start],
			as_dict=True,
		)
	return {
		"doctype": doctype,
		"columns": cols,
		"rows": rows,
		"total": total,
		"start": start,
		"page_length": page_length,
		"has_more": start + len(rows) < total,
		"printable": doctype in ("Sales Invoice", "POS Invoice"),
	}
