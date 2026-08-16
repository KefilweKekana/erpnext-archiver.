"""Bootstrap clean ERPNext site for documentation screenshots."""

from __future__ import annotations


def run():
	import frappe
	from frappe.utils import add_days, getdate, now_datetime, random_string

	frappe.set_user("Administrator")

	# --- Setup wizard / company ---
	if not frappe.get_all("Company"):
		from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

		args = frappe._dict(
			{
				"language": "English",
				"country": "United States",
				"timezone": "America/New_York",
				"currency": "USD",
				"full_name": "Administrator",
				"email": "admin@example.com",
				"company_name": "Demo Trading Co",
				"company_abbr": "DTC",
				"chart_of_accounts": "Standard",
				"fy_start_date": "2026-01-01",
				"fy_end_date": "2026-12-31",
				"setup_website": 0,
			}
		)
		try:
			setup_complete(args)
		except Exception as exc:
			# Some versions expect JSON string
			print("setup_complete retry", exc)
			setup_complete(frappe.as_json(args))
		frappe.db.commit()
		print("setup complete")
	else:
		print("company already present", frappe.get_all("Company", pluck="name"))

	company = frappe.db.get_value("Company", {}, "name")
	print("company", company)

	# Ensure FY 2024/2025/2026
	for name, start, end in (
		("2024", "2024-01-01", "2024-12-31"),
		("2025", "2025-01-01", "2025-12-31"),
		("2026", "2026-01-01", "2026-12-31"),
	):
		if frappe.db.exists("Fiscal Year", name):
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Fiscal Year",
				"year": name,
				"year_start_date": start,
				"year_end_date": end,
			}
		)
		# Some sites use name = year
		doc.insert(ignore_permissions=True)
		print("FY created", name)
	frappe.db.commit()

	# Link companies to FYs if needed
	for fy_name in ("2024", "2025", "2026"):
		if not frappe.db.exists("Fiscal Year", fy_name):
			continue
		fy = frappe.get_doc("Fiscal Year", fy_name)
		existing = {r.company for r in (fy.companies or [])}
		if company and company not in existing:
			fy.append("companies", {"company": company})
			fy.save(ignore_permissions=True)
	frappe.db.commit()

	account = frappe.db.get_value(
		"Account",
		{"company": company, "account_type": "Cash", "is_group": 0},
		"name",
	) or frappe.db.get_value("Account", {"company": company, "is_group": 0}, "name")
	print("account", account)
	if not account:
		frappe.throw("No ledger account found after setup")

	from erpnext_data_archiver.install import seed_default_rules
	from erpnext_data_archiver.archiver import engine

	seed_default_rules()
	settings = frappe.get_single("Archive Settings")
	settings.enabled = 1
	settings.require_backup_before_archive = 1
	settings.last_backup_id = "demo-backup-2026-08-16"
	settings.last_backup_checksum = "sha256:demo-verified-restore"
	settings.confirmation_phrase = "ARCHIVE"
	settings.archive_through_year = "2025"
	settings.cutoff_date = "2026-01-01"
	settings.batch_size = 500
	settings.save(ignore_permissions=True)
	frappe.db.commit()

	cutoff = getdate("2026-01-01")
	existing = frappe.db.sql(
		"SELECT COUNT(*) FROM `tabGL Entry` WHERE posting_date < %s AND voucher_type=%s",
		(cutoff, "EDA Seed"),
	)[0][0]
	need = max(0, 600 - int(existing))
	if need:
		now = now_datetime()
		posting = add_days(cutoff, -45)
		for _ in range(need):
			name = ("EDA-" + random_string(10)).upper()
			frappe.db.sql(
				"""
				INSERT INTO `tabGL Entry`
				(name, creation, modified, modified_by, owner, docstatus, idx,
				 posting_date, account, company, debit, credit,
				 voucher_type, voucher_no, remarks, is_cancelled)
				VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
				""",
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
					125.0,
					0.0,
					"EDA Seed",
					name,
					"Screenshot demo seed",
					0,
				),
			)
		frappe.db.commit()
		print("seeded", need)

	# Clear stuck locks
	from erpnext_data_archiver.archiver import preflight

	frappe.cache().delete_value(preflight.LOCK_KEY + ":" + frappe.local.site)

	run_name = engine.run_archive()
	print("archive run", run_name)
	print("years", engine.get_archived_year_stats())
	print(
		"apps",
		frappe.get_installed_apps(),
	)
	return {"ok": True, "run": run_name, "years": engine.get_archived_year_stats()}
