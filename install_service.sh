#!/bin/bash

# Install Weather Storm Detection System as systemd services

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
CURRENT_USER=$(whoami)

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

echo "🔧 Installing Weather Storm Detection System as systemd services"
echo "================================================================"
echo ""

# Create weather monitoring service
print_info "Creating weather monitoring service..."
sudo tee /etc/systemd/system/weather-monitor.service > /dev/null << EOF
[Unit]
Description=Weather Storm Detection System
After=network.target
Wants=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$SCRIPT_DIR
Environment=PATH=$SCRIPT_DIR/weather_env/bin
ExecStart=$SCRIPT_DIR/weather_env/bin/python $SCRIPT_DIR/main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Create web interface service
print_info "Creating web interface service..."
sudo tee /etc/systemd/system/weather-web.service > /dev/null << EOF
[Unit]
Description=Weather Storm Detection Web Interface
After=network.target weather-monitor.service
Wants=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$SCRIPT_DIR
Environment=PATH=$SCRIPT_DIR/weather_env/bin
ExecStart=$SCRIPT_DIR/weather_env/bin/python $SCRIPT_DIR/web_app.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable services
print_info "Reloading systemd daemon..."
sudo systemctl daemon-reload

print_info "Enabling services to start at boot..."
sudo systemctl enable weather-monitor.service
sudo systemctl enable weather-web.service

echo ""
print_status "Systemd services installed successfully!"
echo ""
echo "🔧 Service Management Commands:"
echo "   Start services:     sudo systemctl start weather-monitor weather-web"
echo "   Stop services:      sudo systemctl stop weather-monitor weather-web"
echo "   Restart services:   sudo systemctl restart weather-monitor weather-web"
echo "   Check status:       sudo systemctl status weather-monitor weather-web"
echo "   View logs:          sudo journalctl -u weather-monitor -f"
echo "                       sudo journalctl -u weather-web -f"
echo "   Disable auto-start: sudo systemctl disable weather-monitor weather-web"
echo ""
echo "✨ Services will now automatically start at system boot!"
echo ""