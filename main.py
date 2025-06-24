#!/usr/bin/env python3
"""
Weather Storm Detection System for Czech Republic (Brno/Reckovice)

A comprehensive weather monitoring system that:
- Fetches data from OpenWeather and Visual Crossing APIs every 10 minutes
- Uses DeepSeek AI for intelligent storm detection
- Sends email alerts for high-confidence storm predictions
- Generates detailed PDF reports
- Runs continuously on Raspberry Pi

Author: Clipron AI
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from scheduler import main

if __name__ == "__main__":
    print("🌩️  Weather Storm Detection System for Czech Republic")
    print("=" * 60)
    print("🏠 Location: Brno/Reckovice, South Moravia")
    print("⏱️  Monitoring Interval: Every 10 minutes")
    print("🧠 AI Analysis: DeepSeek Reasoner")
    print("📧 Email Alerts: High-confidence storms only")
    print("📊 PDF Reports: Detailed weather analysis")
    print("🔄 Daily Summary: 9:00 AM")
    print("=" * 60)
    print()
    
    try:
        print("🚀 Starting monitoring system...")
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 System stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)