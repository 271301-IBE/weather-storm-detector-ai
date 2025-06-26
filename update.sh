#!/bin/bash

# Weather Storm Detection System - Update Script

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

echo "🔄 Aktualizuji Weather Storm Detection System..."

# Activate virtual environment
source weather_env/bin/activate

# Update Python packages
pip install --upgrade -r requirements.txt

# Restart service if running
if systemctl is-active --quiet weather-monitor; then
    sudo systemctl restart weather-monitor
    echo "✅ Služba restartována"
fi

echo "✅ Systém aktualizován"
