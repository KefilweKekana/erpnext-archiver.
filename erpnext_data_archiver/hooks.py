app_name = "erpnext_data_archiver"
app_title = "ERPNext Data Archiver"
app_publisher = "Hiraal"
app_description = (
    "Long-term fiscal-year data archiving for ERPNext v14-v16. Moves old fiscal-year "
    "data into shadow archive tables so the live database stays small and fast, while "
    "summary financial reports automatically include archived data and users can "
    "retrieve selected archive years on demand."
)
app_email = "info@hiraalhealth.so"
app_license = "MIT"
required_apps = ["frappe", "erpnext"]

# ---------- Install / Migrate / Uninstall ----------
after_install = "erpnext_data_archiver.install.after_install"
after_migrate = "erpnext_data_archiver.install.after_migrate"
before_uninstall = "erpnext_data_archiver.install.before_uninstall"

# ---------- Boot ----------
boot_session = "erpnext_data_archiver.api.boot_session"

# ---------- Scheduled Tasks ----------
scheduler_events = {
    "daily": [
        "erpnext_data_archiver.tasks.auto_archive_check",
    ],
}

# ---------- Web Include (Desk) ----------
# Bundle path works with Frappe v15+ esbuild; plain asset path covers v14 and
# sites that have not rebuilt yet. Page JS also injects the stylesheet.
app_include_js = "/assets/erpnext_data_archiver/js/archive_indicator.js"
app_include_css = [
	"erpnext_data_archiver.bundle.css",
	"/assets/erpnext_data_archiver/css/archiver.css?v=1.1.4",
]

# ---------------------------------------------------------------------------
# Install the transparent query-rewrite layer and the report wrappers.
# hooks.py is imported once per worker process, so this is the earliest safe
# place to patch Database.sql for every request/job on sites that have this
# app installed (the patch itself re-checks per-site at query time).
# ---------------------------------------------------------------------------
try:
    from erpnext_data_archiver.archiver import query_patch, report_patches

    query_patch.install()
    report_patches.install()
except Exception:
    # Never let a patching problem break site boot; errors surface in the
    # Archive Settings diagnostics panel instead.
    pass
