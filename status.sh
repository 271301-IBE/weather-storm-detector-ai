#!/bin/bash

# Weather Storm Detection System - Status Checker

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

echo "📊 Weather Storm Detection System - Status Check"
echo "==============================================="
echo ""

# Function to check process status
check_process_status() {
    local process_name="$1"
    local pid_file="$2"
    local log_file="$3"
    
    if [[ -f "$pid_file" ]]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            local uptime=$(ps -o etime= -p "$pid" | tr -d ' ')
            print_status "$process_name is RUNNING (PID: $pid, Uptime: $uptime)"
            
            # Show recent log entries if log file exists
            if [[ -f "$log_file" ]]; then
                echo "   📝 Recent log entries:"
                tail -n 3 "$log_file" 2>/dev/null | while read line; do
                    echo "      $line"
                done
            fi
        else
            print_error "$process_name is NOT RUNNING (stale PID file)"
            rm -f "$pid_file"
        fi
    else
        print_error "$process_name is NOT RUNNING (no PID file)"
    fi
    echo ""
}

# Check weather monitoring system
check_process_status "Weather Monitoring System" "weather_monitor.pid" "logs/weather_monitor.log"

# Check web interface
check_process_status "Web Interface" "web_interface.pid" "logs/web_interface.log"

# Check systemd service if exists
if systemctl list-unit-files weather-monitor.service > /dev/null 2>&1; then
    if systemctl is-active --quiet weather-monitor; then
        print_status "Systemd service weather-monitor is ACTIVE"
    else
        print_warning "Systemd service weather-monitor is INACTIVE"
    fi
    echo ""
fi

# Check network connectivity
print_info "Testing network connectivity..."
if ping -c 1 8.8.8.8 > /dev/null 2>&1; then
    print_status "Internet connectivity: OK"
else
    print_error "Internet connectivity: FAILED"
fi

# Check web interface accessibility
NETWORK_IP=$(hostname -I | awk '{print $1}')
if curl -s http://localhost:5000 > /dev/null 2>&1; then
    print_status "Web interface accessibility: OK"
    echo "   🌐 Dashboard: http://localhost:5000"
    echo "   🌐 Network:   http://$NETWORK_IP:5000"
else
    print_warning "Web interface not accessible on localhost:5000"
fi

echo ""

# Show disk usage
print_info "System Resources:"
echo "   💾 Disk usage in current directory:"
du -sh . 2>/dev/null || echo "      Unable to check disk usage"

if [[ -f "weather_data.db" ]]; then
    db_size=$(du -sh weather_data.db | cut -f1)
    echo "   🗄️  Database size: $db_size"
fi

# Show log file sizes
if [[ -d "logs" ]]; then
    echo "   📝 Log files:"
    ls -lh logs/ 2>/dev/null | grep -v '^total' | while read line; do
        echo "      $line"
    done
fi

echo ""

# Check if processes are actually working (recent activity)
if [[ -f "logs/weather_monitor.log" ]]; then
    recent_activity=$(grep "$(date '+%Y-%m-%d')" logs/weather_monitor.log | tail -1)
    if [[ -n "$recent_activity" ]]; then
        print_status "Weather system shows recent activity today"
        echo "   📅 Latest: $recent_activity"
    else
        print_warning "No recent activity found in weather logs today"
    fi
fi

echo ""
print_info "Commands:"
echo "   Start all:    ./run_all.sh"
echo "   Stop all:     ./stop_all.sh"
echo "   View logs:    tail -f logs/weather_monitor.log"
echo "   Live web:     tail -f logs/web_interface.log"
echo ""