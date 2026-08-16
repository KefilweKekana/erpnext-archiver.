"""Wrappers that make summary / balance-forward reports archive-aware.

Date-range routing (Dagaar RPT-001..003):
  - active-only → no archive UNION (live + opening state)
  - archive-only → rewrite with matching archive years
  - combined → rewrite with all archived years for the historical portion

Never default to include_archives(None) / ALL_YEARS for every wrapped report.
"""

import functools
import importlib

import frappe

from erpnext_data_archiver.archiver.query_patch import include_archives
from erpnext_data_archiver.archiver.routing import (
	MODE_ACTIVE,
	MODE_ARCHIVE,
	MODE_COMBINED,
	extract_dates_from_filters,
	resolve_report_mode,
)

TARGETS = [
	("erpnext.accounts.report.financial_statements", ["get_data"]),
	("erpnext.accounts.report.balance_sheet.balance_sheet", ["execute"]),
	(
		"erpnext.accounts.report.profit_and_loss_statement.profit_and_loss_statement",
		["execute"],
	),
	("erpnext.accounts.report.cash_flow.cash_flow", ["execute"]),
	("erpnext.accounts.report.trial_balance.trial_balance", ["execute", "get_data"]),
	(
		"erpnext.accounts.report.consolidated_financial_statement.consolidated_financial_statement",
		["execute"],
	),
	("erpnext.accounts.report.general_ledger.general_ledger", ["execute"]),
	(
		"erpnext.accounts.report.accounts_receivable.accounts_receivable",
		["ReceivablePayableReport.run", "execute"],
	),
	("erpnext.accounts.report.accounts_payable.accounts_payable", ["execute"]),
	(
		"erpnext.accounts.report.accounts_receivable_summary.accounts_receivable_summary",
		["AccountsReceivableSummary.run", "execute"],
	),
	(
		"erpnext.accounts.report.accounts_payable_summary.accounts_payable_summary",
		["AccountsPayableSummary.run", "execute"],
	),
	(
		"erpnext.accounts.report.trial_balance_for_party.trial_balance_for_party",
		["execute"],
	),
	("erpnext.stock.report.stock_balance.stock_balance", ["execute", "StockBalanceReport.run"]),
	("erpnext.stock.report.stock_ledger.stock_ledger", ["execute"]),
	("erpnext.stock.report.stock_ageing.stock_ageing", ["execute"]),
]

PATCH_STATUS = {"wrapped": [], "skipped": []}
_INSTALLED = False


def _filters_from_args(args, kwargs):
	if kwargs.get("filters") is not None:
		return kwargs.get("filters")
	if args:
		return args[0]
	return {}


def _wrap_callable(fn):
	if getattr(fn, "_eda_wrapped", False):
		return fn

	@functools.wraps(fn)
	def inner(*args, **kwargs):
		filters = _filters_from_args(args, kwargs)
		dates = extract_dates_from_filters(filters)
		try:
			from erpnext_data_archiver.archiver.engine import get_archive_cutoff

			cutoff = get_archive_cutoff()
		except Exception:
			cutoff = None

		fy_start = fy_end = None
		if dates.get("fiscal_year"):
			try:
				row = frappe.db.get_value(
					"Fiscal Year",
					dates["fiscal_year"],
					["year_start_date", "year_end_date"],
					as_dict=True,
				)
				if row:
					fy_start, fy_end = row.year_start_date, row.year_end_date
			except Exception:
				pass

		mode = resolve_report_mode(
			from_date=dates.get("from_date"),
			to_date=dates.get("to_date"),
			cutoff=cutoff,
			fiscal_year=dates.get("fiscal_year"),
			fiscal_year_start=fy_start,
			fiscal_year_end=fy_end,
		)

		if mode == MODE_ACTIVE:
			# Hot path: no archive rewrite
			return fn(*args, **kwargs)

		# Archive / combined: rewrite SELECTs. Report WHERE clauses keep
		# the date scope; years_for_mode("*") means all archive partitions.
		from erpnext_data_archiver.archiver.routing import years_for_mode

		years = years_for_mode(mode, cutoff)
		if years is not None:
			with include_archives(None if years == "*" else years):
				return fn(*args, **kwargs)
		return fn(*args, **kwargs)

	inner._eda_wrapped = True
	return inner


def _patch_attribute(module, attr_path):
	parts = attr_path.split(".")
	owner = module
	for part in parts[:-1]:
		owner = getattr(owner, part, None)
		if owner is None:
			return False
	leaf = parts[-1]
	fn = getattr(owner, leaf, None)
	if not callable(fn):
		return False
	if getattr(fn, "_eda_wrapped", False):
		return True
	setattr(owner, leaf, _wrap_callable(fn))
	return True


def install():
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	for module_path, attrs in TARGETS:
		try:
			module = importlib.import_module(module_path)
		except Exception:
			PATCH_STATUS["skipped"].append(f"{module_path} (module not found)")
			continue
		for attr in attrs:
			try:
				if _patch_attribute(module, attr):
					PATCH_STATUS["wrapped"].append(f"{module_path}:{attr}")
				else:
					PATCH_STATUS["skipped"].append(f"{module_path}:{attr} (attr missing)")
			except Exception as exc:
				PATCH_STATUS["skipped"].append(f"{module_path}:{attr} ({exc})")


def get_patch_status():
	return {
		"wrapped": list(PATCH_STATUS["wrapped"]),
		"skipped": list(PATCH_STATUS["skipped"]),
	}
