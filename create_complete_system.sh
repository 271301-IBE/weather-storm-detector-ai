#!/bin/bash

# Complete Weather Storm Detection System Creator
# Tento script vytvoří všechny soubory najednou na Raspberry Pi

echo "🌩️ Vytváření kompletního Weather Storm Detection System"
echo "======================================================"

# Create main directory
mkdir -p ~/weather-storm-detector
cd ~/weather-storm-detector

echo "📁 Vytvářím adresářovou strukturu..."
mkdir -p logs reports temp ChmiWarnings

echo "📄 Vytvářím konfiguračních soubory..."

# Create requirements.txt
cat > requirements.txt << 'EOF'
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

# Create main.py
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

# Create the full setup.sh from the original
cat > setup.sh << 'SETUP_EOF'