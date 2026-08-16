"""Date-range archive query modes: active / archive / combined."""

from __future__ import annotations

from datetime import date
from typing import Any

from frappe.utils import getdate

MODE_ACTIVE = "active"
MODE_ARCHIVE = "archive"
MODE_COMBINED = "combined"


def resolve_report_mode(
	from_date=None,
	to_date=None,
	cutoff=None,
	fiscal_year=None,
	fiscal_year_start=None,
	fiscal_year_end=None,
) -> str:
	"""Pick routing mode from report date filters vs archive cutoff.

	- Entirely on/after cutoff → active (live + opening state; no archive UNION)
	- Entirely before cutoff → archive
	- Spans cutoff or missing bounds with historical intent → combined
	"""
	cutoff_d = getdate(cutoff) if cutoff else None
	if not cutoff_d:
		return MODE_ACTIVE

	start = _coerce_date(from_date) or _coerce_date(fiscal_year_start)
	end = _coerce_date(to_date) or _coerce_date(fiscal_year_end)

	if start is None and end is None:
		# No dates: balance-forward reports need continuity via openings only
		# on the hot path — do not pull all archives.
		return MODE_ACTIVE

	if end is not None and end < cutoff_d:
		return MODE_ARCHIVE
	if start is not None and start >= cutoff_d:
		return MODE_ACTIVE
	if start is not None and end is not None and start < cutoff_d <= end:
		return MODE_COMBINED
	if start is not None and start < cutoff_d and end is None:
		return MODE_COMBINED
	if end is not None and end >= cutoff_d and start is None:
		return MODE_COMBINED
	return MODE_ACTIVE


def extract_dates_from_filters(filters: Any) -> dict:
	"""Normalize ERPNext report filters (dict or object) to date keys."""
	if filters is None:
		return {}
	if hasattr(filters, "items") and not isinstance(filters, dict):
		try:
			filters = dict(filters)
		except Exception:
			filters = {}
	if not isinstance(filters, dict):
		try:
			filters = filters.as_dict()  # type: ignore[attr-defined]
		except Exception:
			return {}

	def g(*keys):
		for k in keys:
			if filters.get(k) not in (None, ""):
				return filters.get(k)
		return None

	return {
		"from_date": g("from_date", "period_start_date", "start_date"),
		"to_date": g("to_date", "period_end_date", "end_date"),
		"fiscal_year": g("fiscal_year"),
		"company": g("company"),
	}


def years_for_mode(mode: str, cutoff, archived_years: list[str] | None = None):
	"""Years list for query_patch, or None for no rewrite (active)."""
	if mode == MODE_ACTIVE:
		return None
	if mode == MODE_ARCHIVE:
		# Caller may pass explicit years; ALL years before cutoff otherwise
		return archived_years if archived_years is not None else "*"
	if mode == MODE_COMBINED:
		return archived_years if archived_years is not None else "*"
	return None


def _coerce_date(value) -> date | None:
	if value in (None, ""):
		return None
	try:
		return getdate(value)
	except Exception:
		return None
