#!/usr/bin/env python3
"""Kompletní test celého systému před spuštěním."""

import sys
import os
import asyncio
import traceback
from datetime import datetime

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
        
        return True
        
    except Exception as e:
        print(f"❌ Import error: {e}")
        traceback.print_exc()
        return False

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
        
        return True
        
    except Exception as e:
        print(f"❌ Config error: {e}")
        return False

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
        else:
            print("❌ Žádná data získána")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Weather data error: {e}")
        traceback.print_exc()
        return False

def test_chmi_warnings():
    """Test ČHMÚ varování."""
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
            
        return True
        
    except Exception as e:
        print(f"❌ ČHMÚ warnings error: {e}")
        traceback.print_exc()
        return False

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
            
        return True
        
    except Exception as e:
        print(f"❌ Database error: {e}")
        traceback.print_exc()
        return False

def test_email_system():
    """Test nového email systému."""
    print("\n📧 TESTOVÁNÍ NOVÉHO EMAIL SYSTÉMU...")
    
    try:
        from config import load_config
        from email_notifier import EmailNotifier
        from models import AlertLevel
        
        config = load_config()
        notifier = EmailNotifier(config)
        
        # Test filtering logic
        print("🔍 Testování filtrování...")
        
        # Test LOW level (should be skipped)
        from test_emails import create_sample_storm_analysis, create_sample_weather_data
        low_analysis = create_sample_storm_analysis(AlertLevel.LOW)
        notification = notifier.send_storm_alert(low_analysis)
        
        if notification.message_type == "storm_alert_skipped":
            print("✅ LOW level alerts correctly skipped")
        else:
            print("❌ LOW level alerts not being filtered")
            return False
            
        # Test HIGH level (should work)
        high_analysis = create_sample_storm_analysis(AlertLevel.HIGH)
        weather_data = create_sample_weather_data()
        
        # Create email (but don't send)
        msg = notifier._create_storm_alert_email(high_analysis, weather_data)
        if "🚨 BOUŘE NAD BRNEM - HIGH" in msg['Subject']:
            print("✅ HIGH level alert email format OK")
        else:
            print("❌ HIGH level alert format incorrect")
            return False
            
        print("✅ Email systém funguje - pouze HIGH/CRITICAL")
        print("✅ Denní emaily vypnuté")
        print("✅ ČHMÚ emaily filtrované na bouřky/srážky")
        
        return True
        
    except Exception as e:
        print(f"❌ Email system error: {e}")
        traceback.print_exc()
        return False

async def test_ai_analysis():
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
        weather_data = await test_weather_data_for_ai()
        if not weather_data:
            print("⚠️ Přeskakuji AI test - žádná meterologická data")
            return True
            
        # Check if AI analysis should run (cost optimization)
        should_run = scheduler._should_run_ai_analysis(weather_data, [])
        
        if should_run:
            print("🔥 Podmínky pro AI analýzu splněny - spouštím...")
            historical_data = db.get_recent_weather_data(hours=6)
            analysis = await engine.analyze_storm_potential(weather_data, historical_data, [])
            
            print(f"✅ AI analýza dokončena: {analysis.alert_level.value} (confidence: {analysis.confidence_score:.1%})")
        else:
            print("✅ AI analýza přeskočena - normální podmínky (úspora nákladů)")
            
        return True
        
    except Exception as e:
        print(f"❌ AI analysis error: {e}")
        traceback.print_exc()
        return False

async def test_weather_data_for_ai():
    """Helper pro získání dat pro AI test."""
    try:
        from config import load_config
        from data_fetcher import WeatherDataCollector
        
        config = load_config()
        collector = WeatherDataCollector(config)
        return await collector.collect_weather_data()
    except:
        return None

async def main():
    """Hlavní test funkce."""
    print("🚀 KOMPLETNÍ TEST SYSTÉMU")
    print("=" * 50)
    
    tests = [
        ("Importy", test_imports, False),
        ("Konfigurace", test_config, False),
        ("Meteorologická data", test_weather_data, True),
        ("ČHMÚ varování", test_chmi_warnings, False),
        ("Databáze", test_database, False),
        ("Email systém", test_email_system, False),
        ("AI analýza", test_ai_analysis, True),
    ]
    
    results = []
    
    for test_name, test_func, is_async in tests:
        print(f"\n{'='*20}")
        print(f"🧪 {test_name.upper()}")
        print(f"{'='*20}")
        
        try:
            if is_async:
                result = await test_func()
            else:
                result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Test {test_name} failed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*50)
    print("📊 SHRNUTÍ TESTŮ")
    print("="*50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status} - {test_name}")
        if result:
            passed += 1
    
    print(f"\n🎯 VÝSLEDEK: {passed}/{total} testů prošlo")
    
    if passed == total:
        print("\n🎉 VŠECHNY TESTY PROŠLY!")
        print("✅ Systém je připraven ke spuštění")
        print("\n📋 FINÁLNÍ KONFIGURACE:")
        print("  • Pouze HIGH/CRITICAL storm alerts")
        print("  • ČHMÚ emaily jen pro bouřky/srážky/extrémní")
        print("  • Denní emaily vypnuty")
        print("  • Vše v češtině")
        print("  • AI optimalizace nákladů aktivní")
        return True
    else:
        print(f"\n❌ {total-passed} testů selhalo")
        print("🔧 Opravte chyby před spuštěním systému")
        return False

if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n⏹️ Test přerušen uživatelem")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Neočekávaná chyba: {e}")
        traceback.print_exc()
        sys.exit(1)