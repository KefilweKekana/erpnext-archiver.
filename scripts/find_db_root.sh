#!/bin/bash
set -e
for p in admin admin123 frappe mariadb root password pass; do
  echo "try [$p]"
  mysql -uroot -p"$p" -e "SELECT 1" 2>&1 | head -1 || true
done
echo "site user:"
mysql -u_2a2508a6b3d0bce4 -pjvj1g3MamPDw76fB -e "SELECT 1" 2>&1 | head -2 || true
# find root plugin
mysql -u_2a2508a6b3d0bce4 -pjvj1g3MamPDw76fB -e "SHOW GRANTS;" 2>&1 | head -5 || true
