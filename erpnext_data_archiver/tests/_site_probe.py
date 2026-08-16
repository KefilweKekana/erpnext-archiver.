def run():
	import frappe

	print("apps", frappe.get_installed_apps())
	print("companies", frappe.get_all("Company", pluck="name"))
	print("fy", frappe.get_all("Fiscal Year", fields=["name", "year_start_date", "year_end_date"]))
	return "ok"
