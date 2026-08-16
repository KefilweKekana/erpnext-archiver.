import frappe

frappe.connect()
frappe.db.sql(
    "UPDATE `tabArchive Run` SET status='Failed' "
    "WHERE status IN ('Validating','Snapshotting','Moving','Reconciling','In Progress','Recovering')"
)
frappe.db.commit()
try:
    from erpnext_data_archiver.archiver import preflight
    key = preflight.LOCK_KEY + ":" + frappe.local.site
    frappe.cache().delete_value(key)
    print("lock cleared", key)
except Exception as e:
    print("lock clear err", e)
print("stuck runs cleared")
