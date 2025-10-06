#!/bin/bash
set -e

echo "[INFO] Updating system..."
sudo apt update && sudo apt upgrade -y

echo "[INFO] Installing dependencies..."
sudo apt install -y python3 python3-pip python3-venv git curl \
    chromium-browser

echo "[INFO] Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo "[INFO] Installing Python requirements..."
pip install --upgrade pip
pip install flask flask-cors pyserial

echo "[INFO] Setup complete!"
echo "---------------------------------------"
echo "To start the app:"
echo "  source venv/bin/activate"
echo "  python app.py"
echo "---------------------------------------"
echo "To run in kiosk mode:"
echo "  chromium-browser --kiosk http://localhost:5000"
