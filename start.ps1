Write-Host "[INFO] Starting Flask dashboard..."
$env:FLASK_ENV = "production"
Start-Process python app.py

Start-Sleep -Seconds 3

# CHROME VERSION
# Start-Process "chrome.exe" "--kiosk http://127.0.0.1:5000"

# Launch Edge in kiosk mode
Start-Process "msedge.exe" "--kiosk http://127.0.0.1:5000 --edge-kiosk-type=fullscreen"
