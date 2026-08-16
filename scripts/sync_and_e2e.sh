#!/bin/bash
set -e
SRC="/mnt/c/Users/USER-PC/Hiraal app & erpnext module/Hiraal/erpnext_data_archiver"
DST="/home/frappe/frappe-bench/apps/erpnext_data_archiver"
cp -a "$SRC/erpnext_data_archiver/archiver/." "$DST/erpnext_data_archiver/archiver/"
mkdir -p "$DST/erpnext_data_archiver/tests"
cp -a "$SRC/erpnext_data_archiver/tests/." "$DST/erpnext_data_archiver/tests/"
cp "$SRC/erpnext_data_archiver/api.py" "$DST/erpnext_data_archiver/api.py"
cp "$SRC/erpnext_data_archiver/install.py" "$DST/erpnext_data_archiver/install.py"
cp "$SRC/erpnext_data_archiver/tasks.py" "$DST/erpnext_data_archiver/tasks.py"
cp "$SRC/erpnext_data_archiver/hooks.py" "$DST/erpnext_data_archiver/hooks.py"
mkdir -p "$DST/erpnext_data_archiver/erpnext_data_archiver/doctype/archive_doctype_rule"
cp -a "$SRC/erpnext_data_archiver/erpnext_data_archiver/doctype/archive_doctype_rule/." "$DST/erpnext_data_archiver/erpnext_data_archiver/doctype/archive_doctype_rule/"
# sync new opening doctypes etc
cp -a "$SRC/erpnext_data_archiver/erpnext_data_archiver/doctype/." "$DST/erpnext_data_archiver/erpnext_data_archiver/doctype/"
echo SYNC_OK
ls "$DST/erpnext_data_archiver/tests"
cd /home/frappe/frappe-bench
bench --site spca.local execute erpnext_data_archiver.tests.e2e_verify.run
