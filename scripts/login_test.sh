#!/bin/bash
cd /home/frappe/frappe-bench
bench --site hiraal.local set-admin-password 'admin'
echo "--- ping ---"
curl -s http://127.0.0.1:8080/api/method/ping
echo
echo "--- login ---"
curl -s -c /tmp/eda.jar -b /tmp/eda.jar -X POST 'http://127.0.0.1:8080/api/method/login' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data 'usr=Administrator&pwd=admin'
echo
echo "--- who ---"
curl -s -c /tmp/eda.jar -b /tmp/eda.jar 'http://127.0.0.1:8080/api/method/frappe.auth.get_logged_user'
echo
