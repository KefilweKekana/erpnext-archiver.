"""Smoke checks for archive-through-year UX + API."""

from __future__ import annotations


def run():
	import frappe
	from frappe.utils import getdate

	from erpnext_data_archiver.archiver import engine, fiscal, preflight
	from erpnext_data_archiver import api

	results = []

	def check(name, ok, detail=""):
		results.append({"name": name, "ok": bool(ok), "detail": detail})
		print(("PASS" if ok else "FAIL"), name, detail)

	# 1) Field exists on Archive Settings
	meta = frappe.get_meta("Archive Settings")
	check("settings_field", meta.has_field("archive_through_year"))

	# 2) Archivable years populated
	years = engine.get_archivable_years()
	check("archivable_years", len(years) >= 1, str(years))

	# 3) Cutoff for 2025
	cutoff = fiscal.cutoff_after_fiscal_year("2025")
	check("cutoff_2025", str(getdate(cutoff)) == "2026-01-01", str(cutoff))

	# 4) get_state includes new keys
	# Bypass role check by calling internals the page uses
	settings = engine.get_settings()
	state_keys_ok = True
	try:
		# Temporarily allow as Administrator
		frappe.set_user("Administrator")
		state = api.get_state()
		state_keys_ok = all(
			k in state
			for k in (
				"archivable_years",
				"archive_through_year",
				"confirmation_phrase",
				"archived_years",
			)
		)
		check("get_state_keys", state_keys_ok, str(sorted(state.keys())))
		check(
			"get_state_archivable",
			len(state.get("archivable_years") or []) >= 1,
			str(state.get("archivable_years")),
		)
	except Exception as exc:
		check("get_state_keys", False, str(exc))

	# 5) preview_archive with fiscal_year (no mutate beyond read)
	try:
		preview = api.preview_archive(fiscal_year="2025")
		check(
			"preview_archive_year",
			preview.get("cutoff_date") == "2026-01-01",
			str({k: preview.get(k) for k in ("ok", "cutoff_date", "fiscal_year", "error")}),
		)
	except Exception as exc:
		check("preview_archive_year", False, str(exc))

	# 6) apply_archive_through_year persists settings
	engine.apply_archive_through_year("2025")
	settings.reload()
	check(
		"persist_through_year",
		settings.archive_through_year == "2025"
		and str(getdate(settings.cutoff_date)) == "2026-01-01",
		f"year={settings.archive_through_year} cutoff={settings.cutoff_date}",
	)

	# 7) Reject archiving current FY if present
	blocked = False
	try:
		engine.apply_archive_through_year("2026")
	except Exception:
		blocked = True
	check("block_current_fy", blocked)

	# 8) Skip nested full archive here — run e2e_verify separately to avoid lock races
	check("smoke_complete", True, "year-picker API path verified")

	failed = [r for r in results if not r["ok"]]
	print("SUMMARY", f"{len(results) - len(failed)}/{len(results)} passed")
	if failed:
		frappe.throw("Smoke checks failed: " + ", ".join(r["name"] for r in failed))
	return {"ok": True, "results": results}
