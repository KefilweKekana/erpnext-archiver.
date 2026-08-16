import frappe

frappe.connect()
for dt in ("Repost Accounting Ledger", "Repost Item Valuation"):
    if not frappe.db.exists("DocType", dt):
        print("skip", dt)
        continue
    # cancel/delete draft or queued
    names = frappe.get_all(dt, pluck="name")
    print(dt, "count", len(names))
    for name in names[:50]:
        try:
            doc = frappe.get_doc(dt, name)
            if getattr(doc, "docstatus", 0) == 0:
                frappe.delete_doc(dt, name, force=1, ignore_permissions=True)
            else:
                # mark completed if possible
                if hasattr(doc, "status"):
                    frappe.db.set_value(dt, name, "status", "Completed")
        except Exception as e:
            print("fail", dt, name, e)
frappe.db.commit()
print("done")
