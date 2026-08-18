"""Search and print invoices that live only in archive tables."""

from __future__ import annotations

import frappe
from frappe.utils import cint

from erpnext_data_archiver.archiver.query_patch import (
	archive_table_name,
	bypass_archives,
	include_archives,
)

PRINTABLE = ("Sales Invoice", "POS Invoice")


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


def search_invoices(query: str, doctype: str = "Sales Invoice", limit: int = 40) -> list[dict]:
	"""Find invoices in live and archive tables by number or customer."""
	doctype = doctype or "Sales Invoice"
	if doctype not in PRINTABLE:
		frappe.throw("Only Sales Invoice and POS Invoice can be reprinted here.")
	q = (query or "").strip()
	if len(q) < 2:
		frappe.throw("Type at least 2 characters (invoice number or customer).")

	live = "tab" + doctype
	arch = archive_table_name(doctype)
	like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
	limit = max(1, min(cint(limit) or 40, 80))

	params = []
	parts = []
	if _table_exists(live):
		parts.append(f"SELECT {_select_clause(live, archived=False)} FROM `{live}` WHERE {_match_clause(live)}")
		params.extend([like, like, like])
	if _table_exists(arch):
		parts.append(f"SELECT {_select_clause(arch, archived=True)} FROM `{arch}` WHERE {_match_clause(arch)}")
		params.extend([like, like, like])
	if not parts:
		return []

	sql = " UNION ALL ".join(parts) + " ORDER BY posting_date DESC, name DESC LIMIT %s"
	params.append(limit)
	with bypass_archives():
		rows = frappe.db.sql(sql, params, as_dict=True)
	return rows


def _match_clause(table: str) -> str:
	clauses = ["`name` LIKE %s"]
	if _has_col(table, "customer"):
		clauses.append("`customer` LIKE %s")
	else:
		clauses.append("0")
	if _has_col(table, "customer_name"):
		clauses.append("`customer_name` LIKE %s")
	else:
		clauses.append("0")
	return "(" + " OR ".join(clauses) + ")"


def _select_clause(table: str, archived: bool) -> str:
	def col(name, fallback="NULL"):
		return f"`{name}`" if _has_col(table, name) else fallback

	fy = "`fiscal_year_archived`" if archived and _has_col(table, "fiscal_year_archived") else "NULL"
	src = "'Archive'" if archived else "'Live'"
	return (
		f"{col('name')} as name, {col('posting_date')} as posting_date, "
		f"{col('customer')} as customer, {col('customer_name')} as customer_name, "
		f"{col('grand_total', '0')} as grand_total, {col('status')} as status, "
		f"{col('currency')} as currency, {src} as source, {fy} as fiscal_year"
	)


def print_invoice(name: str, doctype: str = "Sales Invoice", print_format: str | None = None) -> dict:
	"""Return print HTML for an invoice in live or archive tables (read-only)."""
	doctype = doctype or "Sales Invoice"
	name = (name or "").strip()
	if not name or doctype not in PRINTABLE:
		frappe.throw("Invoice is required.")
	if not frappe.has_permission(doctype, "read"):
		frappe.throw("You cannot print this document.", frappe.PermissionError)

	years = _years_for_invoice(doctype, name)
	with include_archives(years):
		if not frappe.db.exists(doctype, name):
			frappe.throw(f"{doctype} {name} was not found in live or archive data.")
		html = frappe.get_print(
			doctype,
			name,
			print_format=print_format or None,
			no_letterhead=0,
		)
	return {
		"ok": True,
		"doctype": doctype,
		"name": name,
		"html": html,
		"title": f"{doctype} {name}",
	}


def _years_for_invoice(doctype: str, name: str):
	arch = archive_table_name(doctype)
	if not _table_exists(arch):
		return None
	with bypass_archives():
		row = frappe.db.sql(
			f"SELECT `fiscal_year_archived` FROM `{arch}` WHERE `name` = %s LIMIT 1",
			(name,),
		)
	if row and row[0][0]:
		return [str(row[0][0])]
	return None
