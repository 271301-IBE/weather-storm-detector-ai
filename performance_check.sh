#!/bin/bash

# Performance Check Script for Weather Storm Detection System

echo "🔍 Weather System Performance Check"
echo "=================================="
echo "$(date)"
echo ""

# Check current system stats
echo "📊 Current System Statistics:"
python3 cpu_monitor.py
echo ""

# Check weather processes
echo "🌤️  Weather System Processes:"
python3 cpu_monitor.py processes
echo ""

# Check systemd service status if available
if systemctl is-active --quiet weather-monitor; then
    echo "🔧 Systemd Service Status:"
    systemctl status weather-monitor --no-pager -l
    echo ""
fi

# Check log files for errors
echo "📋 Recent Error Log Entries:"
if [[ -f weather_monitor.log ]]; then
    tail -20 weather_monitor.log | grep -i error || echo "No recent errors found"
else
    echo "No log file found"
fi
echo ""

# Check database size
echo "💾 Database Information:"
if [[ -f weather_data.db ]]; then
    db_size=$(du -h weather_data.db | cut -f1)
    echo "Database size: $db_size"
    
    # Check table sizes
    sqlite3 weather_data.db "SELECT name FROM sqlite_master WHERE type='table';" | while read table; do
        count=$(sqlite3 weather_data.db "SELECT COUNT(*) FROM $table;")
        echo "  $table: $count records"
    done
else
    echo "No database file found"
fi
echo ""

# Check current configuration
echo "⚙️  Current Configuration:"
if [[ -f .env ]]; then
    echo "Monitoring interval: $(grep MONITORING_INTERVAL_MINUTES .env | cut -d'=' -f2) minutes"
    echo "Local forecast interval: $(grep LOCAL_FORECAST_INTERVAL_MINUTES .env | cut -d'=' -f2) minutes"
    echo "Ensemble forecast interval: $(grep ENSEMBLE_FORECAST_INTERVAL_MINUTES .env | cut -d'=' -f2) minutes"
    echo "DeepSeek forecast interval: $(grep DEEPSEEK_FORECAST_INTERVAL_HOURS .env | cut -d'=' -f2) hours"
    echo "CPU threshold: $(grep MAX_CPU_USAGE_THRESHOLD .env | cut -d'=' -f2)%"
    echo "Storm confidence threshold: $(grep STORM_CONFIDENCE_THRESHOLD .env | cut -d'=' -f2)"
else
    echo "No .env configuration file found"
fi
echo ""

# Recommendations
echo "💡 Performance Recommendations:"
cpu_usage=$(python3 -c "import psutil; print(f'{psutil.cpu_percent(interval=1):.1f}')")
memory_usage=$(python3 -c "import psutil; print(f'{psutil.virtual_memory().percent:.1f}')")

if (( $(echo "$cpu_usage > 70" | bc -l) )); then
    echo "  ⚠️  High CPU usage detected ($cpu_usage%). Consider:"
    echo "     - Increasing monitoring intervals"
    echo "     - Reducing forecast frequency"
    echo "     - Lowering CPU threshold"
fi

if (( $(echo "$memory_usage > 80" | bc -l) )); then
    echo "  ⚠️  High memory usage detected ($memory_usage%). Consider:"
    echo "     - Restarting the system"
    echo "     - Checking for memory leaks"
fi

# Check temperature if available
if [[ -f /sys/class/thermal/thermal_zone0/temp ]]; then
    temp_raw=$(cat /sys/class/thermal/thermal_zone0/temp)
    temp_c=$(echo "scale=1; $temp_raw / 1000" | bc)
    if (( $(echo "$temp_c > 70" | bc -l) )); then
        echo "  🌡️  High temperature detected ($temp_c°C). Consider:"
        echo "     - Improving cooling"
        echo "     - Reducing CPU-intensive tasks"
    fi
fi

echo ""
echo "✅ Performance check completed"