#!/bin/bash

# Weather Storm Detection System - Stop Script

echo "🛑 Zastavuji Weather Storm Detection System..."

# Kill any running instances
pkill -f "python.*main.py"

# If systemd service exists, stop it
if systemctl is-active --quiet weather-monitor; then
    sudo systemctl stop weather-monitor
    echo "✅ Systemd služba zastavena"
fi

echo "✅ Systém zastaven"
