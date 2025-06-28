#!/bin/bash

# Weather Storm Detection System - Complete Background Runner
# This script starts both the main weather monitoring system and web interface
# and keeps them running in the background even after terminal is closed

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

echo "🌩️ Weather Storm Detection System - Complete Startup"
echo "====================================================="
echo ""

# Check if virtual environment exists
if [[ ! -d "weather_env" ]]; then
    print_error "Virtual environment not found! Run setup.sh first"
    exit 1
fi

# Check if .env exists
if [[ ! -f .env ]]; then
    print_error ".env file not found! Run setup.sh first"
    exit 1
fi

# Activate virtual environment
source weather_env/bin/activate

# Install Flask if not already installed
print_info "Ensuring Flask is installed..."
pip install flask==2.3.3 > /dev/null 2>&1

# Stop any existing processes
print_info "Stopping any existing processes..."
pkill -f "python.*main.py" > /dev/null 2>&1
pkill -f "python.*web_app.py" > /dev/null 2>&1
pkill -f "thunderstorm_predictor.py" > /dev/null 2>&1


# Create logs directory if it doesn't exist
mkdir -p logs

# Function to check if process is running
check_process() {
    local process_name="$1"
    local pid_file="$2"
    
    if [[ -f "$pid_file" ]]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0  # Process is running
        else
            rm -f "$pid_file"  # Remove stale PID file
            return 1  # Process not running
        fi
    else
        return 1  # PID file doesn't exist
    fi
}

# Start main weather monitoring system
print_info "Starting main weather monitoring system..."
nohup python3 main.py > logs/weather_monitor.log 2>&1 &
WEATHER_PID=$!
echo $WEATHER_PID > weather_monitor.pid

# Wait a moment to check if it started successfully
sleep 3
if ps -p $WEATHER_PID > /dev/null; then
    print_status "Weather monitoring system started (PID: $WEATHER_PID)"
else
    print_error "Failed to start weather monitoring system"
    exit 1
fi

# Start web interface
print_info "Starting web interface..."
nohup python3 web_app.py > logs/web_interface.log 2>&1 &
WEB_PID=$!
echo $WEB_PID > web_interface.pid

# Wait a moment to check if it started successfully
sleep 3
if ps -p $WEB_PID > /dev/null; then
    print_status "Web interface started (PID: $WEB_PID)"
else
    print_error "Failed to start web interface"
    exit 1
fi

# Start thunderstorm predictor loop
print_info "Starting thunderstorm predictor..."
nohup bash -c 'while true; do python3 thunderstorm_predictor.py; sleep 300; done' > logs/thunderstorm_predictor.log 2>&1 &
PREDICTOR_PID=$!
echo $PREDICTOR_PID > thunderstorm_predictor.pid

# Wait a moment to check if it started successfully
sleep 3
if ps -p $PREDICTOR_PID > /dev/null; then
    print_status "Thunderstorm predictor started (PID: $PREDICTOR_PID)"
else
    print_error "Failed to start thunderstorm predictor"
    exit 1
fi

# Get network IP
NETWORK_IP=$(hostname -I | awk '{print $1}')

echo ""
echo "🎉 SYSTEM SUCCESSFULLY STARTED!"
echo "==============================="
echo ""
print_status "Weather monitoring system is running in background"
print_status "Web interface is running in background"
print_status "Thunderstorm predictor is running in background"
echo ""
echo "📊 Web Dashboard Access:"
echo "   Local:    http://localhost:5000"
echo "   Network:  http://$NETWORK_IP:5000"
echo ""
echo "📋 Login Credentials:"
echo "   Username: pi"
echo "   Password: pica1234"
echo ""
echo "📝 Log Files:"
echo "   Weather System: logs/weather_monitor.log"
echo "   Web Interface:  logs/web_interface.log"
echo "   Predictor:      logs/thunderstorm_predictor.log"
echo ""
echo "🔧 Process Management:"
echo "   Weather PID: $WEATHER_PID (saved to weather_monitor.pid)"
echo "   Web PID:     $WEB_PID (saved to web_interface.pid)"
echo "   Predictor PID: $PREDICTOR_PID (saved to thunderstorm_predictor.pid)"
echo ""
echo "⚡ Control Commands:"
echo "   Stop all:     ./stop_all.sh"
echo "   Check status: ./status.sh"
echo "   View logs:    tail -f logs/weather_monitor.log"
echo "                 tail -f logs/web_interface.log"
echo "                 tail -f logs/thunderstorm_predictor.log"
echo ""
print_info "All processes are running in background and will continue even if you close this terminal"
print_info "The system will monitor weather conditions every 10 minutes and provide web dashboard access"
echo ""