#!/bin/bash
set -e
SRC="/mnt/c/Users/USER-PC/Hiraal app & erpnext module/Hiraal/erpnext_data_archiver"
DST="/home/frappe/frappe-bench/apps/erpnext_data_archiver"
cp "$SRC/erpnext_data_archiver/archiver/preflight.py" "$DST/erpnext_data_archiver/archiver/preflight.py"
cp "$SRC/erpnext_data_archiver/archiver/engine.py" "$DST/erpnext_data_archiver/archiver/engine.py"
cp "$SRC/erpnext_data_archiver/tests/e2e_verify.py" "$DST/erpnext_data_archiver/tests/e2e_verify.py"
cd /home/frappe/frappe-bench
# mark stuck runs as Failed and clear lock
bench --site spca.local execute frappe.client.set_value --kwargs "{'doctype':'Archive Run','name':'EDA-RUN-2026-00077','fieldname':'status','value':'Failed'}" 2>/dev/null || true
bench --site spca.local mysql -e "UPDATE \`tabArchive Run\` SET status='Failed' WHERE status IN ('Validating','Snapshotting','Moving','Reconciling','In Progress','Recovering');" 2>/dev/null || true
bench --site spca.local execute erpnext_data_archiver.tests.e2e_verify.run
