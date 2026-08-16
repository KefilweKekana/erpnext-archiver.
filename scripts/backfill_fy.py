import frappe
from frappe.utils import getdate

frappe.connect()
# Inspect archive FY tags
rows = frappe.db.sql(
    "SELECT fiscal_year_archived, COUNT(*) FROM `tabGL Entry Archive` GROUP BY fiscal_year_archived"
)
print("archive fy tags", rows)
fys = frappe.get_all("Fiscal Year", fields=["name", "year_start_date", "year_end_date"], order_by="year_start_date")
print("fiscal years", fys)

# Backfill null FY from Fiscal Year by archived_on / a mid date
# Seed used posting_date = cutoff-30 = 2025-12-02
posting = getdate("2025-12-02")
fy = None
for f in fys:
    if getdate(f.year_start_date) <= posting <= getdate(f.year_end_date):
        fy = f.name
        break
if not fy and fys:
    # create a matching FY if missing
    doc = frappe.get_doc({
        "doctype": "Fiscal Year",
        "year": "2025",
        "year_start_date": "2025-01-01",
        "year_end_date": "2025-12-31",
    })
    try:
        doc.insert(ignore_permissions=True)
        fy = doc.name
        print("created FY", fy)
    except Exception as e:
        print("create fy err", e)
        fy = "2025"

if fy:
    frappe.db.sql(
        "UPDATE `tabGL Entry Archive` SET fiscal_year_archived=%s WHERE fiscal_year_archived IS NULL",
        (fy,),
    )
    if not frappe.db.exists("Archived Fiscal Year", fy):
        d = frappe.get_doc({"doctype": "Archived Fiscal Year", "fiscal_year": fy, "archived_on": frappe.utils.now()})
        d.insert(ignore_permissions=True)
    frappe.db.commit()
    print("backfilled", fy, frappe.db.sql("SELECT fiscal_year_archived, COUNT(*) FROM `tabGL Entry Archive` GROUP BY fiscal_year_archived"))
