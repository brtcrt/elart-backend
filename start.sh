#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "[INFO] Starting Flask dashboard..."
python3 app.py &

# wait for Flask to come up
sleep 3

# open Chromium in kiosk mode
chromium-browser --kiosk http://localhost:5000
