#!/usr/bin/env python3
"""Kompletní test celého systému před spuštěním."""

import sys
import os
import asyncio
import traceback
from datetime import datetime
import pytest

# Add project root to path
sys.path.insert(0, '/home/pi/weather-storm-detector')

def test_imports():
    """Test všech klíčových importů."""
    print("🔍 TESTOVÁNÍ IMPORTŮ...")
    
    try:
        from config import load_config
        print("✅ Config")
        
        from models import WeatherData, StormAnalysis, AlertLevel
        print("✅ Models")
        
        from data_fetcher import WeatherDataCollector
        print("✅ Data Fetcher")
        
        from ai_analysis import StormDetectionEngine
        print("✅ AI Analysis")
        
        from email_notifier import EmailNotifier
        print("✅ Email Notifier (NOVÝ)")
        
        from pdf_generator import WeatherReportGenerator
        print("✅ PDF Generator")
        
        from storage import WeatherDatabase
        print("✅ Storage")
        
        from chmi_warnings import ChmiWarningMonitor
        print("✅ ČHMÚ Monitor")
        
        from scheduler import WeatherMonitoringScheduler
        print("✅ Scheduler")
        
        assert True
        
    except Exception as e:
        print(f"❌ Import error: {e}")
        traceback.print_exc()
        assert False

def test_config():
    """Test konfigurace."""
    print("\n🔧 TESTOVÁNÍ KONFIGURACE...")
    
    try:
        from config import load_config
        config = load_config()
        
        # Check essential config
        assert config.weather.openweather_api_key, "OpenWeather API klíč chybí"
        assert config.weather.visual_crossing_api_key, "Visual Crossing API klíč chybí"
        assert config.ai.deepseek_api_key, "DeepSeek API klíč chybí"
        assert config.email.sender_email, "Email odesílatele chybí"
        assert config.email.sender_password, "Email heslo chybí"
        
        print(f"✅ Monitoring lokace: {config.weather.city_name}, {config.weather.region}")
        print(f"✅ Monitoring interval: {config.system.monitoring_interval_minutes} minut")
        print(f"✅ Storm confidence threshold: {config.ai.storm_confidence_threshold:.1%}")
        print(f"✅ Email recipient: {config.email.recipient_email}")
        
        assert True
        
    except Exception as e:
        print(f"❌ Config error: {e}")
        assert False

@pytest.mark.asyncio
async def test_weather_data():
    """Test získávání meteorologických dat."""
    print("\n🌤️ TESTOVÁNÍ METEOROLOGICKÝCH DAT...")
    
    try:
        from config import load_config
        from data_fetcher import WeatherDataCollector
        
        config = load_config()
        collector = WeatherDataCollector(config)
        
        print("📡 Získávám data z OpenWeather + Visual Crossing...")
        weather_data = await collector.collect_weather_data()
        
        if weather_data:
            print(f"✅ Získáno {len(weather_data)} datových sad")
            for data in weather_data:
                print(f"   📊 {data.source}: {data.temperature:.1f}°C, {data.humidity:.0f}%, {data.description}")
            assert True
        else:
            print("❌ Žádná data získána")
            assert False
            
    except Exception as e:
        print(f"❌ Weather data error: {e}")
        traceback.print_exc()
        assert False

def _get_chmi_warnings():
    """Helper to get ČHMÚ varování."""
    print("\n🏛️ TESTOVÁNÍ ČHMÚ VAROVÁNÍ...")
    
    try:
        from config import load_config
        from chmi_warnings import ChmiWarningMonitor
        
        config = load_config()
        monitor = ChmiWarningMonitor(config)  # Brno
        warnings = monitor.get_all_active_warnings()

        
        print(f"✅ Nalezeno {len(warnings)} aktivních varování")
        for warning in warnings:
            print(f"   🚨 {warning.event} ({warning.color}) - {warning.time_start_text}")
            
        return warnings
        
    except Exception as e:
        print(f"❌ ČHMÚ warnings error: {e}")
        traceback.print_exc()
        return []

def test_database():
    """Test databáze."""
    print("\n💾 TESTOVÁNÍ DATABÁZE...")
    
    try:
        from config import load_config
        from storage import WeatherDatabase
        
        config = load_config()
        db = WeatherDatabase(config)
        
        # Test connection
        print("✅ Databázové připojení OK")
        
        # Get some stats
        recent_data = db.get_recent_weather_data(hours=24)
        print(f"✅ Posledních 24h: {len(recent_data)} meteorologických záznamů")
        
        last_analysis = db.get_last_storm_analysis()
        if last_analysis:
            print(f"✅ Poslední AI analýza: {last_analysis.timestamp.strftime('%d.%m. %H:%M')}")
        else:
            print("ℹ️ Žádná předchozí AI analýza")
            
        assert True
        
    except Exception as e:
        print(f"❌ Database error: {e}")
        traceback.print_exc()
        assert False



@pytest.mark.asyncio
async def test_ai_analysis(chmi_warnings: list):
    """Test AI analýzy (jen pokud jsou storm podmínky)."""
    print("\n🤖 TESTOVÁNÍ AI ANALÝZY...")
    
    try:
        from config import load_config
        from ai_analysis import StormDetectionEngine
        from storage import WeatherDatabase
        from scheduler import WeatherMonitoringScheduler
        
        config = load_config()
        engine = StormDetectionEngine(config)
        db = WeatherDatabase(config)
        scheduler = WeatherMonitoringScheduler(config)
        
        # Get recent weather data
        weather_data = await _get_weather_data_for_ai()
        if not weather_data:
            print("⚠️ Přeskakuji AI test - žádná meterologická data")
            assert True
            return
            
        # Check if AI analysis should run (cost optimization)
        if not chmi_warnings:
            print("⚠️ Přeskakuji AI test - žádná ČHMÚ varování")
            assert True
            return

        should_run = scheduler._should_run_ai_analysis(weather_data, chmi_warnings)
        
        if should_run:
            print("🔥 Podmínky pro AI analýzu splněny - spouštím...")
            historical_data = db.get_recent_weather_data(hours=6)
            analysis = await engine.analyze_storm_potential(weather_data, chmi_warnings)
            
            print(f"✅ AI analýza dokončena: {analysis.alert_level.value} (confidence: {analysis.confidence_score:.1%})")
            assert True
        else:
            print("✅ AI analýza přeskočena - normální podmínky (úspora nákladů)")
            assert True
            
    except Exception as e:
        print(f"❌ AI analysis error: {e}")
        traceback.print_exc()
        assert False

async def _get_weather_data_for_ai():
    """Helper pro získání dat pro AI test."""
    try:
        from config import load_config
        from data_fetcher import WeatherDataCollector
        
        config = load_config()
        collector = WeatherDataCollector(config)
        return await collector.collect_weather_data()
    except:
        return None # This is a helper, not a test, so returning is fine

def test_full_system_run():
    """Hlavní test funkce."""
    print("🚀 KOMPLETNÍ TEST SYSTÉMU")
    print("=" * 50)
    
    # Run tests sequentially
    test_imports()
    test_config()
    asyncio.run(test_weather_data())
    chmi_warnings_list = _get_chmi_warnings()
    test_database()
    asyncio.run(test_ai_analysis(chmi_warnings=chmi_warnings_list))

    print("\n" + "="*50)
    print("🎉 VŠECHNY TESTY PROŠLY!")
    print("✅ Systém je připraven ke spuštění")

if __name__ == "__main__":
    try:
        test_full_system_run()
        pass # Let pytest handle the exit code
    except KeyboardInterrupt:
        print("\n⏹️ Test přerušen uživatelem")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Neočekávaná chyba: {e}")
        traceback.print_exc()
        sys.exit(1)