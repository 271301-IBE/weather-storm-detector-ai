#!/bin/bash

# Weather Storm Detection System - Complete Setup Script
# Tento script nainstaluje a nakonfiguruje celý systém pro detekci bouří

set -e  # Exit on any error

echo "🌩️ Weather Storm Detection System - Setup Script"
echo "=================================================="
echo "Tento script nainstaluje a nakonfiguruje kompletní systém."
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
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

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   print_error "Nespouštějte tento script jako root!"
   exit 1
fi

# Detect OS
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
    print_info "Detekován Linux systém"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
    print_info "Detekován macOS systém"
else
    print_error "Nepodporovaný operační systém: $OSTYPE"
    exit 1
fi

# Step 1: System dependencies
echo ""
echo "📦 Krok 1: Instalace systémových závislostí"
echo "============================================"

if [[ "$OS" == "linux" ]]; then
    # Update package list
    print_info "Aktualizace seznamu balíčků..."
    sudo apt update

    # Install system dependencies
    print_info "Instalace systémových balíčků..."
    sudo apt install -y python3 python3-pip python3-venv git curl wget \
                        build-essential libssl-dev libffi-dev python3-dev \
                        sqlite3 cron systemd bc \
                        libjpeg-dev zlib1g-dev libpng-dev libtiff-dev \
                        libfreetype6-dev liblcms2-dev libwebp-dev

    print_status "Systémové balíčky nainstalovány"

elif [[ "$OS" == "macos" ]]; then
    # Check if Homebrew is installed
    if ! command -v brew &> /dev/null; then
        print_info "Instalace Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi

    # Install dependencies via Homebrew
    print_info "Instalace závislostí přes Homebrew..."
    brew install python3 git sqlite3

    print_status "Systémové balíčky nainstalovány"
fi

# Step 2: Python environment setup
echo ""
echo "🐍 Krok 2: Nastavení Python prostředí"
echo "======================================"

# Check Python version
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
print_info "Detekována Python verze: $PYTHON_VERSION"

# Skip version check - commented out
# if [[ $(echo "$PYTHON_VERSION < 3.8" | bc -l) -eq 1 ]]; then
#     print_error "Vyžadována Python verze 3.8 nebo vyšší!"
#     exit 1
# fi

# Create virtual environment
print_info "Vytváření virtuálního prostředí..."
python3 -m venv weather_env

# Activate virtual environment
print_info "Aktivace virtuálního prostředí..."
source weather_env/bin/activate

# Upgrade pip
print_info "Aktualizace pip..."
pip install --upgrade pip

# Install Python dependencies
print_info "Instalace Python závislostí..."
cat > requirements.txt << EOF
aiohttp==3.9.1
asyncio-throttle==1.0.2
APScheduler==3.10.4
requests==2.31.0
python-dotenv==1.0.0
psutil==5.9.6
reportlab==4.0.7
lxml==4.9.3
python-dateutil==2.8.2
pytz==2023.3
aiosqlite==0.19.0
EOF

pip install -r requirements.txt

print_status "Python prostředí nastaveno"

# Step 3: Configuration
echo ""
echo "⚙️  Krok 3: Konfigurace systému"
echo "==============================="

# Create .env file with user input
print_info "Nastavení konfigurace..."

echo "Zadejte prosím následující údaje:"
echo ""

# Weather API keys
echo "🌤️  API klíče pro počasí:"
read -p "OpenWeather API klíč: " OPENWEATHER_KEY
read -p "Visual Crossing API klíč: " VISUAL_CROSSING_KEY

echo ""
echo "🤖 DeepSeek AI API:"
read -p "DeepSeek API klíč: " DEEPSEEK_KEY

echo ""
echo "📧 Email konfigurace:"
read -p "Odesílací email (Seznam.cz): " SENDER_EMAIL
read -s -p "Heslo k emailu: " SENDER_PASSWORD
echo ""
read -p "Příjemce emailů: " RECIPIENT_EMAIL

echo ""
echo "📍 Lokace:"
read -p "Název města [Brno]: " CITY_NAME
CITY_NAME=${CITY_NAME:-Brno}
read -p "Region [South Moravia]: " REGION
REGION=${REGION:-"South Moravia"}
read -p "Zeměpisná šířka [49.2384]: " LATITUDE
LATITUDE=${LATITUDE:-49.2384}
read -p "Zeměpisná délka [16.6073]: " LONGITUDE
LONGITUDE=${LONGITUDE:-16.6073}

# Create .env file
cat > .env << EOF
# Weather API Configuration
OPENWEATHER_API_KEY=$OPENWEATHER_KEY
VISUAL_CROSSING_API_KEY=$VISUAL_CROSSING_KEY

# Location Configuration
CITY_NAME=$CITY_NAME
REGION=$REGION
LATITUDE=$LATITUDE
LONGITUDE=$LONGITUDE

# AI Configuration
DEEPSEEK_API_KEY=$DEEPSEEK_KEY
DEEPSEEK_API_URL=https://api.deepseek.com/v1
STORM_CONFIDENCE_THRESHOLD=0.99

# Email Configuration
SMTP_SERVER=smtp.seznam.cz
SMTP_PORT=465
SMTP_USE_SSL=true
SENDER_EMAIL=$SENDER_EMAIL
SENDER_PASSWORD=$SENDER_PASSWORD
SENDER_NAME=Clipron AI Weather Detection
RECIPIENT_EMAIL=$RECIPIENT_EMAIL
EMAIL_DELAY_MINUTES=30

# System Configuration
MONITORING_INTERVAL_MINUTES=10
DAILY_SUMMARY_HOUR=9
DATABASE_PATH=./weather_data.db
EOF

print_status "Konfigurace vytvořena"

# Step 4: Directory structure
echo ""
echo "📁 Krok 4: Vytváření adresářové struktury"
echo "========================================"

# Create necessary directories
mkdir -p logs reports temp

print_status "Adresářová struktura vytvořena"

# Step 5: Database initialization
echo ""
echo "🗄️  Krok 5: Inicializace databáze"
echo "================================="

print_info "Vytváření databáze..."
python3 -c "
from storage import WeatherDatabase
from config import load_config
config = load_config()
db = WeatherDatabase(config)
print('Databáze inicializována úspěšně')
"

print_status "Databáze připravena"

# Step 6: System testing
echo ""
echo "🧪 Krok 6: Testování systému"
echo "==========================="

print_info "Spouštím testy systému..."
if python3 test_system.py > test_output.log 2>&1; then
    print_status "Všechny testy prošly úspěšně!"
else
    print_warning "Některé testy selhaly. Zkontrolujte test_output.log"
fi

# Step 7: Service setup (Linux only)
if [[ "$OS" == "linux" ]]; then
    echo ""
    echo "🔧 Krok 7: Nastavení systemd služby"
    echo "==================================="

    read -p "Chcete nastavit automatické spouštění při startu? (y/N): " AUTO_START
    if [[ $AUTO_START =~ ^[Yy]$ ]]; then
        CURRENT_DIR=$(pwd)
        CURRENT_USER=$(whoami)

        # Create systemd service file
        sudo tee /etc/systemd/system/weather-monitor.service > /dev/null << EOF
[Unit]
Description=Weather Storm Detection System
After=network.target
Wants=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$CURRENT_DIR
Environment=PATH=$CURRENT_DIR/weather_env/bin
ExecStart=$CURRENT_DIR/weather_env/bin/python $CURRENT_DIR/main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

        # Reload systemd and enable service
        sudo systemctl daemon-reload
        sudo systemctl enable weather-monitor.service

        print_status "Systemd služba nakonfigurována"
        print_info "Pro spuštění: sudo systemctl start weather-monitor"
        print_info "Pro zastavení: sudo systemctl stop weather-monitor"
        print_info "Pro status: sudo systemctl status weather-monitor"
    fi
fi

# Step 8: Final configuration
echo ""
echo "🎯 Krok 8: Finální nastavení"
echo "============================"

# Create main.py if it doesn't exist
if [[ ! -f "main.py" ]]; then
    cat > main.py << 'EOF'
#!/usr/bin/env python3
"""
Main entry point for Weather Storm Detection System
"""

import asyncio
import sys
import os

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scheduler import main

if __name__ == "__main__":
    print("🌩️ Starting Weather Storm Detection System...")
    asyncio.run(main())
EOF

    chmod +x main.py
    print_status "main.py vytvořen"
fi

# Create start script
cat > start.sh << 'EOF'
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
EOF

chmod +x start.sh

# Create stop script
cat > stop.sh << 'EOF'
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
EOF

chmod +x stop.sh

# Create update script
cat > update.sh << 'EOF'
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
EOF

chmod +x update.sh

print_status "Skripty pro správu vytvořeny"

# Step 9: Quick test
echo ""
echo "🚀 Krok 9: Závěrečný test"
echo "========================"

print_info "Spouštím rychlý test konfigurace..."
if python3 -c "
from config import load_config
config = load_config()
print('✅ Konfigurace v pořádku')
print(f'📍 Lokace: {config.weather.city_name}, {config.weather.region}')
print(f'📧 Email: {config.email.sender_email} -> {config.email.recipient_email}')
print(f'🔑 API klíče: OpenWeather={\"✓\" if config.weather.openweather_api_key else \"✗\"}, Visual Crossing={\"✓\" if config.weather.visual_crossing_api_key else \"✗\"}, DeepSeek={\"✓\" if config.ai.deepseek_api_key else \"✗\"}')
"; then
    print_status "Konfigurace ověřena"
else
    print_error "Problém s konfigurací!"
    exit 1
fi

# Final summary
echo ""
echo "🎉 INSTALACE DOKONČENA!"
echo "======================"
echo ""
print_status "Weather Storm Detection System je připraven k použití!"
echo ""
echo "📋 Přehled souborů:"
echo "   🔧 setup.sh      - Tento instalační script"
echo "   🚀 start.sh      - Spuštění systému"
echo "   🛑 stop.sh       - Zastavení systému"
echo "   🔄 update.sh     - Aktualizace systému"
echo "   ⚙️  .env          - Konfigurace (NEMAZAT!)"
echo "   📊 main.py       - Hlavní spouštěcí soubor"
echo ""
echo "🚀 Jak spustit:"
echo "   Manuálně:     ./start.sh"
if [[ "$OS" == "linux" && $AUTO_START =~ ^[Yy]$ ]]; then
echo "   Jako služba:  sudo systemctl start weather-monitor"
fi
echo ""
echo "📧 Systém bude:"
echo "   🔄 Každých 10 minut kontrolovat počasí"
echo "   🌅 Každý den v 9:00 poslat shrnutí s AI obsahem"
echo "   ⚡ Poslat varování při detekci bouře (AI + ČHMÚ data)"
echo "   🏛️ Kontrolovat oficiální ČHMÚ varování"
echo ""
echo "📝 Logy najdete v:"
echo "   📁 logs/          - Aplikační logy"
echo "   📁 reports/       - PDF reporty"
if [[ "$OS" == "linux" ]]; then
echo "   📋 journalctl -u weather-monitor -f  - Systemd logy"
fi
echo ""
print_info "Pro spuštění testů: python3 test_system.py"
print_info "Pro pokročilé testy: python3 test_combined_system.py"
echo ""
print_warning "DŮLEŽITÉ: Soubor .env obsahuje citlivé údaje - nemazat a nesdílet!"
echo ""
echo "🎯 Systém je připraven detekovat bouře a posílat chytrá varování!"
echo "   Používá AI analýzu kombinovanou s oficiálními ČHMÚ daty"
echo "   Posílá pouze vysoce spolehlivá varování (>99% jistota)"
echo "   Denní shrnutí generované AI v češtině"
echo ""
print_status "Instalace úspěšně dokončena! 🌩️"