"""Unit tests for routing, manifest checksums, and opening-state keys.

These tests do not require a Frappe site. Run::

    python -m pytest erpnext_data_archiver/tests -q
"""

from __future__ import annotations

import sys
import types
import unittest
from datetime import date
from pathlib import Path

# Ensure app package is importable when tests run from repo root.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
	sys.path.insert(0, str(ROOT))

# Lightweight frappe stub for modules that import frappe at load time.
if "frappe" not in sys.modules:
	frappe_stub = types.ModuleType("frappe")

	class _ValidationError(Exception):
		pass

	frappe_stub.ValidationError = _ValidationError
	frappe_stub.utils = types.ModuleType("frappe.utils")

	def getdate(v):
		if v is None or v == "":
			return None
		if isinstance(v, date):
			return v
		if hasattr(v, "year"):
			return date(v.year, v.month, v.day)
		parts = str(v)[:10].split("-")
		return date(int(parts[0]), int(parts[1]), int(parts[2]))

	def flt(v):
		try:
			return float(v or 0)
		except Exception:
			return 0.0

	def cint(v):
		try:
			return int(float(v or 0))
		except Exception:
			return 0

	def add_days(d, days):
		from datetime import timedelta

		base = getdate(d)
		if base is None:
			return None
		return base + timedelta(days=int(days))

	def throw(msg, *args, **kwargs):
		raise frappe_stub.ValidationError(msg)

	def nowdate():
		return "2026-08-18"

	frappe_stub.throw = throw
	frappe_stub.utils.getdate = getdate
	frappe_stub.utils.flt = flt
	frappe_stub.utils.cint = cint
	frappe_stub.utils.add_days = add_days
	frappe_stub.utils.nowdate = nowdate
	sys.modules["frappe"] = frappe_stub
	sys.modules["frappe.utils"] = frappe_stub.utils


from erpnext_data_archiver.archiver.manifest import (  # noqa: E402
	batch_checksum,
	pick_critical_fields,
	row_fingerprint,
	verify_batch,
)
from erpnext_data_archiver.archiver.opening_state import make_idempotency_key  # noqa: E402
from erpnext_data_archiver.archiver.routing import (  # noqa: E402
	MODE_ACTIVE,
	MODE_ARCHIVE,
	MODE_COMBINED,
	extract_dates_from_filters,
	resolve_report_mode,
)


class TestRouting(unittest.TestCase):
	def test_active_when_range_after_cutoff(self):
		mode = resolve_report_mode(
			from_date="2026-01-01",
			to_date="2026-06-30",
			cutoff="2026-01-01",
		)
		self.assertEqual(mode, MODE_ACTIVE)

	def test_archive_when_range_before_cutoff(self):
		mode = resolve_report_mode(
			from_date="2024-01-01",
			to_date="2024-12-31",
			cutoff="2025-01-01",
		)
		self.assertEqual(mode, MODE_ARCHIVE)

	def test_combined_when_range_spans_cutoff(self):
		mode = resolve_report_mode(
			from_date="2024-07-01",
			to_date="2025-06-30",
			cutoff="2025-01-01",
		)
		self.assertEqual(mode, MODE_COMBINED)

	def test_no_dates_defaults_active_hot_path(self):
		mode = resolve_report_mode(cutoff="2025-01-01")
		self.assertEqual(mode, MODE_ACTIVE)

	def test_years_for_mode(self):
		from erpnext_data_archiver.archiver.routing import years_for_mode

		self.assertIsNone(years_for_mode(MODE_ACTIVE, "2026-01-01"))
		self.assertEqual(years_for_mode(MODE_ARCHIVE, "2026-01-01"), "*")
		self.assertEqual(years_for_mode(MODE_COMBINED, "2026-01-01", ["2024", "2025"]), ["2024", "2025"])


class TestManifest(unittest.TestCase):
	def test_checksum_order_independent(self):
		a = batch_checksum(["b", "a"])
		b = batch_checksum(["a", "b"])
		self.assertEqual(a, b)

	def test_verify_batch_passes(self):
		h = batch_checksum(["x"])
		verify_batch(1, 1, h, h)

	def test_verify_batch_count_mismatch(self):
		h = batch_checksum(["x"])
		with self.assertRaises(ValueError):
			verify_batch(2, 1, h, h)

	def test_verify_batch_hash_mismatch(self):
		with self.assertRaises(ValueError):
			verify_batch(1, 1, "aaa", "bbb")

	def test_pick_critical_fields(self):
		cols = ["name", "debit", "foo", "actual_qty"]
		picked = pick_critical_fields(cols)
		self.assertIn("name", picked)
		self.assertIn("debit", picked)
		self.assertIn("actual_qty", picked)

	def test_row_fingerprint_stable(self):
		f1 = row_fingerprint({"name": "X", "debit": 1}, ["name", "debit"])
		f2 = row_fingerprint({"name": "X", "debit": 1}, ["name", "debit"])
		self.assertEqual(f1, f2)


class TestOpeningKeys(unittest.TestCase):
	def test_idempotent_key(self):
		a = make_idempotency_key("gl", "2025-01-01", "Co", "Cash", None)
		b = make_idempotency_key("gl", "2025-01-01", "Co", "Cash", None)
		self.assertEqual(a, b)

	def test_different_inputs_differ(self):
		a = make_idempotency_key("gl", "2025-01-01", "Co", "Cash")
		b = make_idempotency_key("gl", "2025-01-01", "Co", "Bank")
		self.assertNotEqual(a, b)


class TestApplyTableUnion(unittest.TestCase):
	"""Regression: aliased FROM/JOIN must not become (subquery) `tabX` alias."""

	def setUp(self):
		from erpnext_data_archiver.archiver.query_patch import apply_table_union

		self.apply = apply_table_union
		self.union = "(SELECT `name` FROM `tabSales Order` UNION ALL SELECT `name` FROM `tabSales Order Archive`)"

	def test_keeps_existing_alias(self):
		q = "SELECT so.name FROM `tabSales Order` so WHERE so.docstatus = 1"
		out = self.apply(q, "tabSales Order", self.union)
		self.assertIn(self.union + " so", out)
		self.assertNotIn(") `tabSales Order` so", out)

	def test_left_join_with_alias(self):
		q = (
			"SELECT * FROM `tabSales Order` so "
			"LEFT JOIN `tabSales Invoice Item` sii ON sii.so_detail = soi.name"
		)
		out = self.apply(q, "tabSales Invoice Item", "(SELECT 1)")
		self.assertIn("LEFT JOIN (SELECT 1) sii ON", out)
		self.assertNotIn(") `tabSales Invoice Item` sii", out)

	def test_no_alias_uses_table_name(self):
		q = "SELECT name FROM `tabSales Order` WHERE docstatus = 1"
		out = self.apply(q, "tabSales Order", self.union)
		self.assertIn(self.union + " `tabSales Order` WHERE", out)

	def test_does_not_treat_left_as_alias(self):
		q = "SELECT * FROM `tabSales Order` LEFT JOIN `tabCustomer` c ON c.name = so.customer"
		out = self.apply(q, "tabSales Order", self.union)
		self.assertIn(self.union + " `tabSales Order` LEFT JOIN", out)

	def test_comma_join_sales_order_analysis_shape(self):
		q = (
			"SELECT so.name FROM\n"
			"\t\t\t`tabSales Order` so,\n"
			"\t\t\t`tabSales Order Item` soi\n"
			"\t\tWHERE soi.parent = so.name"
		)
		# Pattern requires FROM/JOIN immediately before table — ERPNext puts
		# newline between FROM and table; ensure we still match via FROM\s+.
		q2 = (
			"SELECT so.name FROM `tabSales Order` so, `tabSales Order Item` soi "
			"WHERE soi.parent = so.name"
		)
		out = self.apply(q2, "tabSales Order", self.union)
		self.assertIn(self.union + " so,", out)
		self.assertNotIn("`tabSales Order` so", out.split(self.union, 1)[-1][:40])


class TestMonthlyCutoff(unittest.TestCase):
	"""Closed-month archive of the current fiscal year (retail / high-volume GL)."""

	def test_cutoff_after_month_july(self):
		from erpnext_data_archiver.archiver.fiscal import cutoff_after_month

		self.assertEqual(cutoff_after_month("2026-07"), date(2026, 8, 1))

	def test_cutoff_after_month_december(self):
		from erpnext_data_archiver.archiver.fiscal import cutoff_after_month

		self.assertEqual(cutoff_after_month("2026-12"), date(2027, 1, 1))

	def test_max_allowed_cutoff_monthly_is_first_of_this_month(self):
		from erpnext_data_archiver.archiver.fiscal import max_allowed_cutoff

		self.assertEqual(max_allowed_cutoff(monthly=True), date(2026, 8, 1))

	def test_list_archivable_months_excludes_current_month(self):
		from erpnext_data_archiver.archiver import fiscal

		orig_start = fiscal.current_fy_start
		orig_fy = fiscal.fiscal_year_for_date
		fiscal.current_fy_start = lambda: date(2026, 1, 1)
		fiscal.fiscal_year_for_date = lambda _d: "2026"
		try:
			months = [m["month"] for m in fiscal.list_archivable_months()]
		finally:
			fiscal.current_fy_start = orig_start
			fiscal.fiscal_year_for_date = orig_fy
		self.assertEqual(months[0], "2026-01")
		self.assertEqual(months[-1], "2026-07")
		self.assertNotIn("2026-08", months)

	def test_invalid_month_is_rejected(self):
		from erpnext_data_archiver.archiver.fiscal import cutoff_after_month

		with self.assertRaises(Exception):
			cutoff_after_month("2026-13")

	def test_cutoff_covers_refuses_same_or_earlier(self):
		from erpnext_data_archiver.archiver.fiscal import cutoff_covers

		self.assertTrue(cutoff_covers("2026-01-01", "2026-01-01"))
		self.assertTrue(cutoff_covers("2026-08-01", "2026-01-01"))
		self.assertFalse(cutoff_covers("2026-01-01", "2026-08-01"))
		self.assertFalse(cutoff_covers(None, "2026-01-01"))


if __name__ == "__main__":
	unittest.main()
