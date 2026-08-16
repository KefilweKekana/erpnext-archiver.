#!/bin/bash
set -e
cd /home/frappe/frappe-bench
bench use hiraal.local
bench set-config -g default_site hiraal.local
# kill old serve if any
pkill -f "bench serve" 2>/dev/null || true
pkill -f "frappe serve" 2>/dev/null || true
sleep 1
nohup bench serve --port 8080 >/tmp/bench-serve-hiraal.log 2>&1 &
sleep 4
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/api/method/ping
echo SERVE_OK
