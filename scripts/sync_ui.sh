#!/bin/bash
set -e
SRC="/mnt/c/Users/USER-PC/Hiraal app & erpnext module/Hiraal/erpnext_data_archiver"
DST="/home/frappe/frappe-bench/apps/erpnext_data_archiver"
APP="$DST/erpnext_data_archiver"
MOD="$APP/erpnext_data_archiver"

cp "$SRC/erpnext_data_archiver/erpnext_data_archiver/page/archive_retrieval/archive_retrieval.js" \
  "$MOD/page/archive_retrieval/archive_retrieval.js"
cp "$SRC/erpnext_data_archiver/api.py" "$APP/api.py"
cp "$SRC/erpnext_data_archiver/hooks.py" "$APP/hooks.py"
# Page JS also injects critical layout styles if assets are missing.
cp "$SRC/erpnext_data_archiver/public/css/archiver.css" "$APP/public/css/archiver.css"
cp "$SRC/erpnext_data_archiver/public/css/erpnext_data_archiver.bundle.css" \
  "$APP/public/css/erpnext_data_archiver.bundle.css"
cp "$SRC/erpnext_data_archiver/archiver/fiscal.py" "$APP/archiver/fiscal.py"
cp "$SRC/erpnext_data_archiver/archiver/engine.py" "$APP/archiver/engine.py"
cp "$SRC/erpnext_data_archiver/archiver/preflight.py" "$APP/archiver/preflight.py"
cp "$SRC/erpnext_data_archiver/archiver/opening_state.py" "$APP/archiver/opening_state.py"
cp "$SRC/erpnext_data_archiver/archiver/query_patch.py" "$APP/archiver/query_patch.py"
cp "$SRC/erpnext_data_archiver/archiver/reconcile.py" "$APP/archiver/reconcile.py"
cp "$SRC/erpnext_data_archiver/install.py" "$APP/install.py"
cp "$SRC/erpnext_data_archiver/erpnext_data_archiver/doctype/archive_settings/archive_settings.json" \
  "$MOD/doctype/archive_settings/archive_settings.json"
cp "$SRC/erpnext_data_archiver/erpnext_data_archiver/doctype/archive_settings/archive_settings.js" \
  "$MOD/doctype/archive_settings/archive_settings.js"
cp "$SRC/erpnext_data_archiver/erpnext_data_archiver/doctype/archive_settings/archive_settings.py" \
  "$MOD/doctype/archive_settings/archive_settings.py"

cd /home/frappe/frappe-bench
bench build --app erpnext_data_archiver
bench --site spca.local migrate
bench --site spca.local clear-cache
echo OK
