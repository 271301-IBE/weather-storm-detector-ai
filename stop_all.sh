#!/bin/bash

# Weather Storm Detection System - Stop All Processes

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

echo "🛑 Stopping Weather Storm Detection System"
echo "=========================================="
echo ""

# Function to stop process by PID file
stop_process_by_pid() {
    local process_name="$1"
    local pid_file="$2"
    
    if [[ -f "$pid_file" ]]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            print_info "Stopping $process_name (PID: $pid)..."
            kill "$pid"
            
            # Wait for graceful shutdown
            local count=0
            while ps -p "$pid" > /dev/null 2>&1 && [ $count -lt 10 ]; do
                sleep 1
                ((count++))
            done
            
            # Force kill if still running
            if ps -p "$pid" > /dev/null 2>&1; then
                print_warning "Force killing $process_name..."
                kill -9 "$pid"
            fi
            
            print_status "$process_name stopped"
        else
            print_warning "$process_name was not running"
        fi
        rm -f "$pid_file"
    else
        print_warning "No PID file found for $process_name"
    fi
}

# Stop weather monitoring system
stop_process_by_pid "Weather monitoring system" "weather_monitor.pid"

# Stop web interface
stop_process_by_pid "Web interface" "web_interface.pid"

# Kill any remaining processes by name
print_info "Cleaning up any remaining processes..."
pkill -f "python.*main.py" > /dev/null 2>&1
pkill -f "python.*web_app.py" > /dev/null 2>&1

# If systemd service exists, stop it
if systemctl is-active --quiet weather-monitor 2>/dev/null; then
    print_info "Stopping systemd service..."
    sudo systemctl stop weather-monitor
    print_status "Systemd service stopped"
fi

echo ""
print_status "All Weather Storm Detection System processes have been stopped"
echo ""
print_info "To start again, run: ./run_all.sh"
echo ""