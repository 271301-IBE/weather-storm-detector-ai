#!/bin/bash

# Weather Storm Detection System - Start Script

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

echo "🌩️ Spouštím Weather Storm Detection System..."

# Activate virtual environment
source weather_env/bin/activate

# Check if .env exists
if [[ ! -f .env ]]; then
    echo "❌ Soubor .env nenalezen! Spusťte nejprve setup.sh"
    exit 1
fi

# Start the system
python3 main.py
