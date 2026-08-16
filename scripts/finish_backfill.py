import frappe
frappe.connect()
frappe.db.sql(
    "UPDATE `tabGL Entry Archive` SET fiscal_year_archived=%s WHERE fiscal_year_archived IS NULL OR fiscal_year_archived=''",
    ("2025",),
)
if not frappe.db.exists("Archived Fiscal Year", "2025"):
    d = frappe.get_doc({"doctype": "Archived Fiscal Year", "fiscal_year": "2025", "archived_on": frappe.utils.now()})
    d.insert(ignore_permissions=True)
frappe.db.commit()
print(frappe.db.sql("SELECT fiscal_year_archived, COUNT(*) FROM `tabGL Entry Archive` GROUP BY fiscal_year_archived"))
print(frappe.get_all("Archived Fiscal Year"))
