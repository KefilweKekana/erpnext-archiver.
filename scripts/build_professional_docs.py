"""Build Product, Testing, and Operator PDFs in Octanode proposal style.

Screenshots are placed under the sections they illustrate — never as a dump
at the end.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from proposal_theme import (  # noqa: E402
	ProposalPDF,
	add_bullet,
	add_callout,
	add_code,
	add_image,
	add_kicker_block,
	add_para,
	add_section_title,
	add_steps,
	add_table,
	draw_contents,
	draw_cover,
)

MANUAL = ROOT / "docs" / "manual"
IMG = MANUAL / "images"


def _pdf(title: str) -> ProposalPDF:
	pdf = ProposalPDF(doc_title=title, brand="Hiraal", format="A4")
	pdf.set_auto_page_break(auto=True, margin=18)
	pdf.set_margins(18, 18, 18)
	pdf.alias_nb_pages()
	return pdf


def build_product() -> Path:
	out = MANUAL / "ERPNext_Data_Archiver_Product_Documentation.pdf"
	pdf = _pdf("ERPNext Data Archiver - Product Documentation")

	draw_cover(
		pdf,
		brand="Hiraal",
		pill="ERPNEXT  ·  DATA ARCHIVER",
		title="ERPNext Data Archiver",
		subtitle="Product Documentation",
		prepared_for=("Your organisation", "ERPNext operators"),
		prepared_by=("Hiraal", "ERPNext Data Archiver"),
		scope=("Version 1.1.0", "ERPNext v14-v16  ·  MariaDB"),
	)

	draw_contents(
		pdf,
		[
			("01", "The One-Page Summary", None),
			("02", "How It Works", None),
			("03", "Install and Roles", None),
			("04", "Configure Archive Settings", None),
			("05", "Run an Archive", None),
			("06", "Retrieve and Restore", None),
			("07", "Operations and Support", None),
		],
	)

	# 01 Summary
	pdf.add_page()
	add_section_title(pdf, "The One-Page Summary", kicker="Section 01")
	add_para(
		pdf,
		"ERPNext Data Archiver moves completed fiscal-year transactional data out of "
		"live tables into same-database shadow tables so the active site stays fast, "
		"while balances and history remain correct when you need them.",
	)
	add_table(
		pdf,
		["Layer", "Today without archive", "After this module"],
		[
			[
				"Live tables",
				"All years compete for indexes and cache",
				"Current FY + open docs only; history moved out",
			],
			[
				"Balances",
				"Reports scan full GL / SLE history",
				"Opening-state synthetics keep current FY correct",
			],
			[
				"History",
				"Always online, always slow",
				"On-demand via date routing or session Retrieve",
			],
			[
				"Safety",
				"Manual cleanup is risky",
				"Preflight checks, backup confirmation, verified move, reconciliation before completion",
			],
		],
		[38, 70, 72],
		caption="Table 1 - What changes for day-to-day ERPNext work",
	)
	add_callout(
		pdf,
		"The promise",
		"Same ERPNext subscription. Same MariaDB. No separate archive server required. "
		"After archive, day-to-day work behaves like a site that started in the current "
		"fiscal year. Historical ranges are served only when explicitly requested.",
	)

	# 02 How it works
	pdf.add_page()
	add_section_title(pdf, "How It Works", kicker="Section 02  ·  Architecture")
	add_kicker_block(pdf, "Hot path vs history")
	add_para(
		pdf,
		"Active (current-period) queries read only live tables plus compact opening-state "
		"snapshots. They never scan archive transaction tables. Archive tables are joined "
		"only for archive-only or cross-year date ranges, or when a user retrieves years.",
	)
	add_table(
		pdf,
		["Mode", "When", "Data sources"],
		[
			["Active", "Range on/after cutoff", "Live + opening state (no archive UNION)"],
			["Archive", "Range entirely before cutoff", "Matching archive partitions"],
			["Combined", "Range spans cutoff", "Live + scoped archive; openings not double-counted"],
			["Session retrieve", "User opt-in on Desk", "Selected archived years in this session"],
		],
		[35, 55, 90],
		caption="Table 2 - Query routing modes",
	)
	add_para(pdf, "Standard ERPNext Desk after login:")
	add_image(pdf, IMG / "01-desk-home.png", "Figure 1 - Desk home")

	# 03 Install
	pdf.add_page()
	add_section_title(pdf, "Install and Roles", kicker="Section 03")
	add_code(
		pdf,
		"bench get-app /path/to/erpnext_data_archiver\n"
		"bench --site your.site install-app erpnext_data_archiver\n"
		"bench --site your.site migrate\n"
		"bench build --app erpnext_data_archiver\n"
		"bench --site your.site clear-cache",
	)
	add_table(
		pdf,
		["Role", "Can do"],
		[
			["System Manager", "Full configure, archive, restore, uninstall policy"],
			["Archive Manager", "Configure, preview, archive, restore, retrieve"],
			["Accounts / Stock Manager", "Browse retrieve / session years (no archive run)"],
		],
		[50, 130],
		caption="Table 3 - Permission matrix",
	)
	add_callout(
		pdf,
		"Uninstall protection",
		"The app cannot be uninstalled while archived fiscal years or archive tables still "
		"hold data. Restore or export history first, then uninstall.",
	)

	# 04 Settings
	pdf.add_page()
	add_section_title(pdf, "Configure Archive Settings", kicker="Section 04")
	add_para(
		pdf,
		"Open Archive Settings from Desk search. Enable the module, record backup evidence, "
		"and choose Archive Through Fiscal Year (preferred) so the cutoff is set automatically.",
	)
	add_image(pdf, IMG / "02-archive-settings.png", "Figure 2 - Archive Settings")
	add_table(
		pdf,
		["Field", "Production", "Notes"],
		[
			["Enabled", "Yes", "Master switch"],
			["Require Backup Reference", "Yes", "Blocks run until backup ID + checksum set"],
			["Last Backup ID / Checksum", "Yes", "Evidence of verified backup"],
			["Confirmation Phrase", "Yes", "Default ARCHIVE"],
			["Archive Through Fiscal Year", "Recommended", "Sets cutoff to day after year ends"],
			["Archive Cutoff Date", "Auto", "Rows before this date are eligible"],
			["Batch Size", "Tune", "Lower on busy sites"],
			["DocType Rules", "Review", "Seeded GL, SLE, invoices, orders, stock..."],
		],
		[55, 30, 95],
		caption="Table 4 - Settings fields",
	)
	add_callout(
		pdf,
		"Archive vs Retrieve",
		"You archive through a fiscal year (or cutoff date). You do not pick years on the "
		"Retrieve page to archive - that list is only for reading already-archived years.",
	)

	# 05 Run archive
	pdf.add_page()
	add_section_title(pdf, "Run an Archive", kicker="Section 05")
	add_kicker_block(pdf, "From Archive Settings")
	add_steps(
		pdf,
		[
			("Record backup evidence", "Set Last Backup ID and Checksum after a verified backup."),
			("Pick the year", "Set Archive Through Fiscal Year (for example 2025)."),
			("Preview", "Preview Archive must show Preflight OK and row estimates."),
			("Confirm and run", "Run Archive Now - type the confirmation phrase."),
			("Watch the run", "Open Archive Run and wait until status is Completed."),
		],
	)
	add_para(pdf, "A successful preview looks like this:")
	add_image(pdf, IMG / "03-preview-archive.png", "Figure 3 - Archive Preview (Preflight OK)")
	add_para(pdf, "When the job finishes, Archive Run shows Completed with evidence:")
	add_image(pdf, IMG / "04-archive-run-completed.png", "Figure 4 - Completed Archive Run")
	add_table(
		pdf,
		["Code", "Meaning", "Action"],
		[
			["PRE-002", "Drafts before cutoff", "Clear or submit drafts"],
			["PRE-003", "Pending reposts", "Finish or cancel repost jobs"],
			["PRE-004", "Another archive already running", "Wait for it to finish, or mark a stuck run Failed"],
			["PRE-006", "Backup missing", "Set Last Backup ID and Checksum"],
		],
		[28, 55, 97],
		caption="Table 5 - Common preflight blockers",
	)
	add_table(
		pdf,
		["Metric", "Before archive", "After archive"],
		[
			["Historical GL (before cutoff)", "Present in live tables", "Moved to archive tables"],
			["Current-year balances", "Built from full history", "Preserved via opening entries"],
			["Archive Run status", "-", "Completed"],
		],
		[60, 55, 65],
		caption="Table 6 - What success looks like",
	)

	# 06 Retrieve / restore
	pdf.add_page()
	add_section_title(pdf, "Retrieve and Restore", kicker="Section 06")
	add_kicker_block(pdf, "Session retrieve (read only)")
	add_para(
		pdf,
		"Path: Retrieve Archived Data. Tick already-archived years, Apply to this session, "
		"then Use live data only to return to the hot path. Retrieval does not move data.",
	)
	add_image(pdf, IMG / "05-retrieve-archived-data.png", "Figure 5 - Retrieve Archived Data (Live mode)")
	add_para(pdf, "After applying year 2025:")
	add_image(
		pdf,
		IMG / "06-retrieve-year-2025-active.png",
		"Figure 6 - Session Archive mode - reading live data plus 2025",
	)
	add_kicker_block(pdf, "Restore a fiscal year")
	add_para(
		pdf,
		"Managers only. Collision dry-run first; resolve or force only after review. "
		"After success, openings are rebuilt for the live cutoff.",
	)

	# 07 Ops
	pdf.add_page()
	add_section_title(pdf, "Operations and Support", kicker="Section 07")
	add_kicker_block(pdf, "Day-to-day checklist")
	for t in [
		"Verified DB (+ files) backup; ID and checksum in Archive Settings",
		"Fiscal Year masters exist for years you will archive",
		"Pending reposts / blocking drafts cleared",
		"Preview = Preflight OK",
		"Archive Run = Completed with evidence JSON",
		"Current FY reports look correct",
		"Optional: retrieve one archived year, then return to live-only",
	]:
		add_bullet(pdf, t)
	pdf.ln(2)
	add_table(
		pdf,
		["Symptom", "Fix"],
		[
			["Archive blocked (PRE-004)", "Wait for the current run, or mark a stuck Archive Run as Failed"],
			["No years on Retrieve page", "Complete at least one successful archive first"],
			["Cannot uninstall the app", "Restore or export archived years, then uninstall"],
			["Archive Run Failed", "Open the run, fix the reported cause, then run again"],
		],
		[50, 130],
		caption="Table 7 - Troubleshooting",
	)

	out.parent.mkdir(parents=True, exist_ok=True)
	pdf.output(str(out))
	print(f"Wrote {out} ({out.stat().st_size} bytes)")
	return out


def build_testing() -> Path:
	out = MANUAL / "ERPNext_Data_Archiver_Testing_Documentation.pdf"
	pdf = _pdf("ERPNext Data Archiver - Testing Documentation")

	draw_cover(
		pdf,
		brand="Hiraal",
		pill="ERPNEXT  ·  ACCEPTANCE",
		title="ERPNext Data Archiver",
		subtitle="Testing Guide",
		prepared_for=("Your team", "Desk walkthrough on ERPNext"),
		prepared_by=("Hiraal", "ERPNext Data Archiver"),
		scope=("Version 1.1.0", "Simple click-through tests"),
	)

	draw_contents(
		pdf,
		[
			("01", "What You Need", None),
			("02", "Test 1 to 5 - Day to Day Checks", None),
			("03", "Test 6 to 7 - Restore and Safety", None),
			("04", "Sign-off", None),
		],
	)

	# 01
	pdf.add_page()
	add_section_title(pdf, "What You Need", kicker="Section 01")
	add_para(
		pdf,
		"This guide is for people who use ERPNext every day. You do not need to use "
		"the command line. Follow each test in order on a staging (practice) site first.",
	)
	add_kicker_block(pdf, "Before you begin")
	for t in [
		"You can log in to ERPNext Desk",
		"Your user is System Manager or Archive Manager",
		"Someone has already installed the Data Archiver app on this site",
		"You have a practice / staging site (do not run the first archive on live production)",
		"A database backup has been taken, and you know the backup ID and checksum to type in",
	]:
		add_bullet(pdf, t)

	# 02 Tests 1-5
	pdf.add_page()
	add_section_title(pdf, "Day to Day Checks", kicker="Section 02  ·  Tests 1 to 5")

	add_kicker_block(pdf, "Test 1 - Open the app and turn it on")
	add_para(pdf, "Check that Archive Settings exists and can be saved.")
	add_steps(
		pdf,
		[
			("Log in to ERPNext", "You should land on Desk with the usual module icons."),
			("Search Archive Settings", "Use the search box at the top. Open Archive Settings."),
			("Turn it on", "Tick Enabled. Tick Require Backup Reference."),
			("Enter backup details", "Type the Last Backup ID and Last Backup Checksum you were given."),
			("Pick a closed year", "In Archive Through Fiscal Year, choose the last closed year (for example 2025)."),
			("Save", "Click Save. Open the page again and check your values are still there."),
		],
	)
	add_image(pdf, IMG / "01-desk-home.png", "Figure 1 - Desk after login")
	add_image(pdf, IMG / "02-archive-settings.png", "Figure 2 - Archive Settings filled in")
	add_table(
		pdf,
		["Pass if...", "Fail if..."],
		[
			[
				"The page opens, Save works, and your values stay after refresh",
				"Archive Settings is missing, or Save shows an error",
			]
		],
		[90, 90],
		caption="Test 1 result",
	)

	pdf.add_page()
	add_kicker_block(pdf, "Test 2 - Preview before archiving")
	add_para(pdf, "Check that the system can review what would be archived safely.")
	add_steps(
		pdf,
		[
			("Stay on Archive Settings", "Same page as Test 1."),
			("Open the menu", "Click the three-dot Menu (or the Preview Archive button if you see it)."),
			("Choose Preview Archive", "A dialog opens with the preview result."),
			("Read the result", "You should see Preflight OK, the year, the cutoff date, and how many rows."),
		],
	)
	add_image(pdf, IMG / "03-preview-archive.png", "Figure 3 - Preview showing Preflight OK")
	add_table(
		pdf,
		["Pass if...", "Fail if..."],
		[
			[
				"The dialog says Preflight OK",
				"It says blocked, or asks for backup details you already entered",
			]
		],
		[90, 90],
		caption="Test 2 result",
	)
	add_callout(
		pdf,
		"If Preview is blocked",
		"Common fixes: enter backup ID and checksum (Test 1), finish or cancel unfinished stock/account "
		"repost jobs, or clear draft documents dated before the cutoff. Ask your implementer if unsure.",
	)

	pdf.add_page()
	add_kicker_block(pdf, "Test 3 - Run the archive")
	add_para(pdf, "Check that archiving finishes successfully.")
	add_steps(
		pdf,
		[
			("On Archive Settings, start the run", "Choose Run Archive Now from the menu."),
			("Type the confirmation word", "Usually ARCHIVE (same as Confirmation Phrase on the form). Submit."),
			("Open Archive Run", "Search Archive Run, or click the run name in the message that appears."),
			("Wait until it finishes", "Status should become Completed (green)."),
			("Glance at Evidence", "You should see report text under Evidence (preflight / reconciliation)."),
		],
	)
	add_image(pdf, IMG / "04-archive-run-completed.png", "Figure 4 - Archive Run Completed")
	add_table(
		pdf,
		["Pass if...", "Fail if..."],
		[
			[
				"Status is Completed",
				"Status is Failed, or it stays stuck for a long time",
			]
		],
		[90, 90],
		caption="Test 3 result",
	)

	pdf.add_page()
	add_kicker_block(pdf, "Test 4 - Check current-year reports still work")
	add_para(pdf, "After archive, normal reports for this year should still open.")
	add_steps(
		pdf,
		[
			("Open Trial Balance", "Go to Accounting, open Trial Balance."),
			("Choose this year", "Pick your company and the current fiscal year. Click to run the report."),
			("Open Balance Sheet", "Same idea: company + current year, then run."),
			("Ask finance to glance", "Numbers should look normal for the current year."),
		],
	)
	add_table(
		pdf,
		["Pass if...", "Fail if..."],
		[
			[
				"Both reports open and finish without an error message",
				"A report errors, hangs, or current-year totals look obviously wrong",
			]
		],
		[90, 90],
		caption="Test 4 result",
	)

	add_kicker_block(pdf, "Test 5 - Browse an archived year (temporary view)")
	add_para(
		pdf,
		"Retrieve only changes what you see in this login session. It does not move data back.",
	)
	add_steps(
		pdf,
		[
			("Search Retrieve Archived Data", "Open that page from Desk search."),
			("Look at Archived years", "You should see the year you archived, with a row count."),
			("Tick the year", "Select it, then click Apply to this session."),
			("Check the banner", "It should say Archive mode (reading live data plus that year)."),
			("Go back to normal", "Click Use live data only. Banner should return to Live mode."),
		],
	)
	add_image(pdf, IMG / "05-retrieve-archived-data.png", "Figure 5 - Retrieve page (Live mode)")
	add_image(
		pdf,
		IMG / "06-retrieve-year-2025-active.png",
		"Figure 6 - After Apply (Archive mode)",
	)
	add_table(
		pdf,
		["Pass if...", "Fail if..."],
		[
			[
				"Year appears, Apply turns Archive mode on, Live mode returns when you click it",
				"No years listed after a Completed archive, or Apply does nothing",
			]
		],
		[90, 90],
		caption="Test 5 result",
	)

	# 03 Tests 6-7
	pdf.add_page()
	add_section_title(pdf, "Restore and Safety", kicker="Section 03  ·  Tests 6 to 7")

	add_kicker_block(pdf, "Test 6 - Restore a year (managers only)")
	add_para(
		pdf,
		"Only do this on a practice site unless your implementer says otherwise. "
		"Restore puts one archived year back into live data.",
	)
	add_steps(
		pdf,
		[
			("Open Retrieve Archived Data", "Same page as Test 5."),
			("Choose Restore a year", "Follow the prompt to pick an archived year."),
			("Read the check first", "The system lists conflicts if any. Ask your implementer before forcing."),
			("Confirm restore", "If the check is clear, confirm and wait until it finishes."),
			("Quick check", "You should be able to see that year's documents again in normal lists."),
		],
	)
	add_table(
		pdf,
		["Pass if...", "Fail if..."],
		[
			[
				"Restore completes and the year is visible again in live data",
				"Restore errors, or you are asked to force without understanding why",
			]
		],
		[90, 90],
		caption="Test 6 result",
	)

	add_kicker_block(pdf, "Test 7 - Do not start two archives at once")
	add_para(pdf, "The system should stop a second archive while one is already running.")
	add_steps(
		pdf,
		[
			("Start one archive", "Use Run Archive Now (only if there is still something left to archive)."),
			("While it is running", "In another browser window, try Run Archive Now again."),
			("Expect a stop message", "The second try should be refused (busy / already running)."),
			("After the first finishes", "When status is Completed, starting a new archive is allowed again."),
		],
	)
	add_table(
		pdf,
		["Pass if...", "Fail if..."],
		[
			[
				"Second archive is blocked while the first is running",
				"Two archives run at the same time with no warning",
			]
		],
		[90, 90],
		caption="Test 7 result",
	)

	# 04 Sign-off
	pdf.add_page()
	add_section_title(pdf, "Sign-off", kicker="Section 04")
	add_para(pdf, "Print this page. For each test, circle Pass or Fail with a pen.")
	add_table(
		pdf,
		["Test", "What you checked", "Result (circle one)"],
		[
			["1", "Archive Settings opens and saves", "Pass    /    Fail"],
			["2", "Preview shows Preflight OK", "Pass    /    Fail"],
			["3", "Archive Run ends as Completed", "Pass    /    Fail"],
			["4", "Trial Balance and Balance Sheet still work", "Pass    /    Fail"],
			["5", "Retrieve year works; Live mode returns", "Pass    /    Fail"],
			["6", "Restore works on practice site (if required)", "Pass    /    Fail"],
			["7", "Second archive is blocked while one runs", "Pass    /    Fail"],
		],
		[18, 100, 52],
		caption="Table - Test results (print and circle)",
	)
	add_callout(
		pdf,
		"Before using this on the live company site",
		"Take a verified backup first. Enter the backup ID and checksum in Archive Settings. "
		"Only then run archive on production. After it completes, ask finance to check "
		"Trial Balance and Balance Sheet for the current year.",
	)
	add_table(
		pdf,
		["Role", "Name", "Date", "Signature"],
		[
			["Tester", "", "", ""],
			["IT / admin", "", "", ""],
			["Finance", "", "", ""],
		],
		[40, 50, 35, 55],
		caption="Table - Sign-off",
	)

	pdf.output(str(out))
	print(f"Wrote {out} ({out.stat().st_size} bytes)")
	return out


def build_operator() -> Path:
	out = MANUAL / "OPERATOR_MANUAL.pdf"
	pdf = _pdf("ERPNext Data Archiver - Operator Manual")

	draw_cover(
		pdf,
		brand="Hiraal",
		pill="ERPNEXT  ·  OPERATOR GUIDE",
		title="ERPNext Data Archiver",
		subtitle="Operator Manual",
		prepared_for=("Site operators", "Archive Manager / System Manager"),
		prepared_by=("Hiraal", "ERPNext Data Archiver"),
		scope=("Version 1.1.0", "ERPNext v14-v16  ·  MariaDB"),
	)

	draw_contents(
		pdf,
		[
			("01", "Quick Start", None),
			("02", "Desk and Settings", None),
			("03", "Preview and Run", None),
			("04", "Retrieve Session", None),
			("05", "Checklist and Troubleshooting", None),
		],
	)

	pdf.add_page()
	add_section_title(pdf, "Quick Start", kicker="Section 01")
	add_steps(
		pdf,
		[
			("Install", "bench migrate and bench build --app erpnext_data_archiver"),
			("Configure", "Archive Settings: Enable, Backup ID + Checksum, Through Year"),
			("Preview", "Preview Archive must be OK"),
			("Run", "Run Archive Now - type ARCHIVE"),
			("Confirm", "Archive Run status = Completed"),
			("Browse if needed", "Retrieve Archived Data is session-only read"),
		],
	)
	add_table(
		pdf,
		["Action", "Where", "What it does"],
		[
			["Archive", "Settings or Run archive", "Moves data out of live through a chosen year"],
			["Retrieve", "Year checkboxes", "Session view only - does not move data"],
			["Restore", "Restore a year", "Copies one archived year back to live"],
		],
		[35, 55, 90],
		caption="Table 1 - Do not confuse Archive and Retrieve",
	)

	pdf.add_page()
	add_section_title(pdf, "Desk and Settings", kicker="Section 02")
	add_para(pdf, "After login, open Desk and search for Archive Settings, Archive Run, or Retrieve.")
	add_image(pdf, IMG / "01-desk-home.png", "Figure 1 - Desk home")
	add_para(pdf, "Configure Archive Settings as below, then Save.")
	add_image(pdf, IMG / "02-archive-settings.png", "Figure 2 - Archive Settings")
	add_table(
		pdf,
		["Field", "Guidance"],
		[
			["Enabled", "Master switch"],
			["Require Backup Reference", "Keep on in production"],
			["Last Backup ID / Checksum", "Verified backup evidence"],
			["Confirmation Phrase", "Default ARCHIVE"],
			["Archive Through Fiscal Year", "Preferred way to choose what to archive"],
			["Archive Cutoff Date", "Auto from year; advanced override"],
		],
		[55, 125],
		caption="Table 2 - Settings fields",
	)

	pdf.add_page()
	add_section_title(pdf, "Preview and Run", kicker="Section 03")
	add_para(pdf, "Click Preview Archive. You should see Preflight OK and estimated row counts.")
	add_image(pdf, IMG / "03-preview-archive.png", "Figure 3 - Archive Preview / Preflight")
	add_para(pdf, "If blocked: clear PRE-002 drafts, PRE-003 reposts, or set PRE-006 backup fields.")
	add_para(
		pdf,
		"Then Run Archive Now, type the confirmation phrase, and wait for Completed.",
	)
	add_image(pdf, IMG / "04-archive-run-completed.png", "Figure 4 - Completed Archive Run")
	add_callout(
		pdf,
		"After a successful run",
		"Historical rows before the cutoff are in archive tables. Current-year balances stay "
		"correct through opening entries. Spot-check Trial Balance and Balance Sheet for the "
		"current year.",
	)

	pdf.add_page()
	add_section_title(pdf, "Retrieve Session", kicker="Section 04")
	add_para(
		pdf,
		"Open Retrieve Archived Data. The year list is for reading years already archived.",
	)
	add_image(pdf, IMG / "05-retrieve-archived-data.png", "Figure 5 - Retrieve Archived Data")
	add_para(pdf, "Tick 2025, Apply to this session - banner becomes Archive mode.")
	add_image(
		pdf,
		IMG / "06-retrieve-year-2025-active.png",
		"Figure 6 - Session archive mode for a selected year",
	)
	add_para(pdf, "Click Use live data only to return to the fast hot path.")
	add_kicker_block(pdf, "Restore")
	add_para(
		pdf,
		"Managers: Restore a year runs collision dry-run first. Resolve collisions or force "
		"only after review. Restore copies archive to live and rebuilds openings.",
	)

	pdf.add_page()
	add_section_title(pdf, "Checklist and Troubleshooting", kicker="Section 05")
	for t in [
		"DB backup ID + checksum recorded",
		"Preview preflight OK",
		"Confirmation phrase entered",
		"Archive Run = Completed (not Failed)",
		"Live historical row counts dropped",
		"Synthetic openings present (voucher_type = Archive Opening)",
		"Spot-check Trial Balance / Balance Sheet for current FY",
		"Retrieve year works; Use live data only restores default",
	]:
		add_bullet(pdf, f"[ ] {t}")
	pdf.ln(2)
	add_table(
		pdf,
		["Symptom", "Fix"],
		[
			["Stuck archive / PRE-004", "Mark the stuck Archive Run as Failed, then try again"],
			["No years on Retrieve page", "Complete at least one successful archive first"],
			["Cannot uninstall the app", "Restore or export archived years first"],
		],
		[50, 130],
		caption="Table 3 - Troubleshooting",
	)

	pdf.output(str(out))
	print(f"Wrote {out} ({out.stat().st_size} bytes)")
	return out


def build_all():
	paths = [build_product(), build_testing(), build_operator()]
	return paths


if __name__ == "__main__":
	build_all()
