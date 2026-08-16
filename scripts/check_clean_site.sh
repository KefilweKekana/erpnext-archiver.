#!/bin/bash
set -e
cd /home/frappe/frappe-bench
SITE=hiraal.local
SRC="/mnt/c/Users/USER-PC/Hiraal app & erpnext module/Hiraal/erpnext_data_archiver"
cp "$SRC/erpnext_data_archiver/tests/prepare_demo_screenshots.py" \
  apps/erpnext_data_archiver/erpnext_data_archiver/tests/prepare_demo_screenshots.py

bench --site "$SITE" list-apps
bench --site "$SITE" console <<'PY'
import frappe
frappe.connect()
print("companies", frappe.get_all("Company", pluck="name"))
print("fy", frappe.get_all("Fiscal Year", pluck="name"))
print("apps", frappe.get_installed_apps())
PY
