#!/bin/bash
set -e
cd /home/frappe/frappe-bench

# Sync latest archiver from Windows source
SRC="/mnt/c/Users/USER-PC/Hiraal app & erpnext module/Hiraal/erpnext_data_archiver"
DST="apps/erpnext_data_archiver"
rsync -a --delete \
  --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
  --exclude 'docs/manual/*.pdf' \
  "$SRC/" "$DST/" || {
  # fallback copy key paths
  cp -a "$SRC/erpnext_data_archiver/." "$DST/erpnext_data_archiver/"
}

SITE=hiraal.local
echo "=== Using clean site: $SITE ==="
bench use "$SITE"
bench --site "$SITE" list-apps

# Install ERPNext if missing
if ! bench --site "$SITE" list-apps | grep -q '^erpnext'; then
  echo "Installing erpnext..."
  bench --site "$SITE" install-app erpnext
fi

# Install archiver
if ! bench --site "$SITE" list-apps | grep -q '^erpnext_data_archiver'; then
  echo "Installing erpnext_data_archiver..."
  bench --site "$SITE" install-app erpnext_data_archiver
else
  bench --site "$SITE" migrate
fi

bench build --app erpnext_data_archiver
bench --site "$SITE" clear-cache

# Set admin password for screenshots
bench --site "$SITE" set-admin-password admin

echo "=== Apps on $SITE ==="
bench --site "$SITE" list-apps
echo OK
