import frappe
frappe.connect()
for status in frappe.db.sql("select name, docstatus, status from `tabRepost Item Valuation` limit 20"):
    print(status)
print("count0", frappe.db.count("Repost Item Valuation", {"docstatus": 0}))
try:
    print("queued", frappe.db.count("Repost Item Valuation", {"status": ["in", ["Queued", "In Progress"]]}))
except Exception as e:
    print(e)
