#!/bin/bash

# Weather Storm Detection System - Web Interface Start Script

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

echo "🌐 Starting Weather Storm Detection Web Interface..."

# Activate virtual environment
source weather_env/bin/activate

# Check if .env exists
if [[ ! -f .env ]]; then
    echo "❌ .env file not found! Run setup.sh first"
    exit 1
fi

# Install Flask if not already installed
pip install flask==2.3.3

echo "🌐 Web interface will be available at:"
echo "   Local:    http://localhost:5000"
echo "   Network:  http://$(hostname -I | awk '{print $1}'):5000"
echo ""
echo "📋 Login credentials:"
echo "   Username: pi"
echo "   Password: pica1234"
echo ""
echo "🔄 Starting web server..."

# Start the web interface
python3 web_app.py