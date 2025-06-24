#!/bin/bash
# Spusť tento script na Raspberry Pi

mkdir -p ~/weather-storm-detector
cd ~/weather-storm-detector

# Vytvoř requirements.txt
cat > requirements.txt << 'REQUIREMENTS'
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
REQUIREMENTS

echo "Requirements.txt vytvořen"
