#!/bin/bash

# Weather Storm Detection System - Start Script

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

echo "🌩️ Spouštím Weather Storm Detection System (Optimized)..."

# Show current system stats
echo "📊 Current system status:"
python3 cpu_monitor.py

# Activate virtual environment
source weather_env/bin/activate

# Check if .env exists
if [[ ! -f .env ]]; then
    echo "❌ Soubor .env nenalezen! Spusťte nejprve setup.sh"
    exit 1
fi

echo "⚡ Optimalized settings:"
echo "  - Monitoring interval: 15 minutes"
echo "  - Local forecast: 10 minutes"
echo "  - Ensemble forecast: 30 minutes"
echo "  - DeepSeek forecast: 8 hours"
echo "  - CPU throttling: 60% threshold"
echo "  - AI triggers: More conservative thresholds"

# Start the system
python3 main.py
