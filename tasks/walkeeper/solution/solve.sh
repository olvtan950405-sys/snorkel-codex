#!/usr/bin/env bash
set -euo pipefail
cd /app
install -m 0644 /solution/planner.py /app/walkeeper/planner.py
rm -rf /app/out
/app/bin/walkeeper
python3 -m py_compile /app/walkeeper/*.py
