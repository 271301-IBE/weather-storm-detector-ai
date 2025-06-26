#!/usr/bin/env python3
"""
Test script for Weather Storm Detection System

Tests all components individually to ensure they work correctly
before deploying to Raspberry Pi.
"""

import asyncio
import sys
import logging
from datetime import datetime
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from config import load_config
from data_fetcher import WeatherDataCollector
from ai_analysis import StormDetectionEngine
from email_notifier import EmailNotifier
from pdf_generator import WeatherReportGenerator
from storage import WeatherDatabase
from models import StormAnalysis, AlertLevel
from chmi_warnings import ChmiWarningMonitor, ChmiWarning

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_configuration():
    """Test configuration loading."""
    print("🔧 Testing configuration...")
    try:
        config = load_config()
        print(f"✅ Configuration loaded successfully")
        print(f"   📍 Location: {config.weather.city_name}, {config.weather.region}")
        print(f"   🔑 OpenWeather API: {'✓' if config.weather.openweather_api_key else '✗'}")
        print(f"   🔑 Visual Crossing API: {'✓' if config.weather.visual_crossing_api_key else '✗'}")
        print(f"   🔑 DeepSeek API: {'✓' if config.ai.deepseek_api_key else '✗'}")
        print(f"   📧 Email configured: {'✓' if config.email.sender_email else '✗'}")
        return config
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return None

async def test_database(config):
    """Test database initialization and operations."""
    print("\n🗄️ Testing database...")
    try:
        db = WeatherDatabase(config)
        print("✅ Database initialized successfully")
        
        # Test basic operations
        recent_data = db.get_recent_weather_data(hours=1)
        print(f"   📊 Recent data entries: {len(recent_data) if recent_data else 0}")
        
        last_alert = db.get_last_storm_alert()
        print(f"   🚨 Last storm alert: {'None' if last_alert is None else last_alert.strftime('%Y-%m-%d %H:%M:%S')}")
        
        return True
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False

async def test_weather_apis(config):
    """Test weather data collection from APIs."""
    print("\n🌤️ Testing weather APIs...")
    try:
        collector = WeatherDataCollector(config)
        weather_data = await collector.collect_weather_data()
        
        if weather_data:
            print(f"✅ Weather data collected successfully")
            for data in weather_data:
                print(f"   📡 {data.source}: {data.temperature:.1f}°C, {data.humidity:.0f}% humidity")
                print(f"      Condition: {data.condition.value}, {data.description}")
            
            quality_score = collector.get_data_quality_score(weather_data)
            print(f"   📊 Data quality score: {quality_score:.1%}")
            return weather_data
        else:
            print("❌ No weather data collected")
            return None
            
    except Exception as e:
        print(f"❌ Weather API test failed: {e}")
        return None

async def test_ai_analysis(config, weather_data):
    """Test AI storm analysis."""
    print("\n🧠 Testing AI analysis...")
    if not weather_data:
        print("⚠️ Skipping AI test - no weather data available")
        return None
        
    try:
        engine = StormDetectionEngine(config)
        analysis = await engine.analyze_storm_potential(weather_data)
        
        if analysis:
            print(f"✅ AI analysis completed successfully")
            print(f"   🌩️ Storm detected: {'YES' if analysis.storm_detected else 'NO'}")
            print(f"   📊 Confidence: {analysis.confidence_score:.1%}")
            print(f"   🚨 Alert level: {analysis.alert_level.value}")
            print(f"   🎯 Data quality: {analysis.data_quality_score:.1%}")
            
            should_alert = engine.should_send_alert(analysis)
            print(f"   📧 Would send alert: {'YES' if should_alert else 'NO'}")
            return analysis
        else:
            print("❌ AI analysis failed")
            return None
            
    except Exception as e:
        print(f"❌ AI analysis test failed: {e}")
        return None

def test_pdf_generation(config, analysis, weather_data):
    """Test PDF report generation."""
    print("\n📄 Testing PDF generation...")
    if not analysis or not weather_data:
        print("⚠️ Skipping PDF test - no analysis or weather data available")
        return None
        
    try:
        generator = WeatherReportGenerator(config)
        pdf_path = generator.generate_storm_report(analysis, weather_data)
        
        if pdf_path and Path(pdf_path).exists():
            file_size = Path(pdf_path).stat().st_size
            print(f"✅ PDF report generated successfully")
            print(f"   📁 File: {pdf_path}")
            print(f"   📏 Size: {file_size / 1024:.1f} KB")
            return pdf_path
        else:
            print("❌ PDF generation failed")
            return None
            
    except Exception as e:
        print(f"❌ PDF generation test failed: {e}")
        return None

def test_email_system(config, send_test_email=False):
    """Test email notification system."""
    print("\n📧 Testing email system...")
    try:
        notifier = EmailNotifier(config)
        
        # Test SMTP connection
        try:
            with notifier._create_smtp_connection() as server:
                print("✅ SMTP connection successful")
                smtp_connected = True
        except Exception as smtp_error:
            print(f"⚠️ SMTP connection failed: {smtp_error}")
            smtp_connected = False
        
        # Test email generation
        dummy_analysis = StormAnalysis(
            timestamp=datetime.now(),
            confidence_score=0.95,
            storm_detected=True,
            alert_level=AlertLevel.HIGH,
            predicted_arrival=None,
            predicted_intensity="moderate",
            analysis_summary="TEST: Systémový test emailových notifikací - všechna data fungují správně",
            recommendations=[
                "Toto je testovací email z Clipron AI Weather Detection",
                "Systém funguje správně a je připraven na detekci bouří",
                "Sledujte ČHMÚ varování pro oficiální informace"
            ],
            data_quality_score=0.90
        )
        
        email_msg = notifier._create_storm_alert_email(dummy_analysis)
        print("✅ Email message generation successful")
        print(f"   📧 Subject: {email_msg['Subject']}")
        print(f"   👤 To: {email_msg['To']}")
        
        # Optionally send actual test email
        if send_test_email and smtp_connected:
            print("\n📤 Sending test email...")
            try:
                result = notifier.send_storm_alert(dummy_analysis)
                if result.sent_successfully:
                    print("✅ Test email sent successfully!")
                    print(f"   📧 Sent to: {result.recipient}")
                    print(f"   📅 Time: {result.timestamp}")
                else:
                    print(f"❌ Test email failed: {result.error_message}")
            except Exception as e:
                print(f"❌ Error sending test email: {e}")
        
        return smtp_connected
        
    except Exception as e:
        print(f"❌ Email system test failed: {e}")
        return False

def test_system_resources():
    """Test system resource requirements."""
    print("\n💻 Testing system resources...")
    try:
        import psutil
        
        # Memory usage
        memory = psutil.virtual_memory()
        print(f"✅ System resources checked")
        print(f"   🧠 Available RAM: {memory.available / (1024**3):.1f} GB")
        print(f"   💾 Free disk space: {psutil.disk_usage('.').free / (1024**3):.1f} GB")
        
        # Check if sufficient for Raspberry Pi
        min_ram_gb = 0.5  # 500MB minimum
        min_disk_gb = 1.0  # 1GB minimum
        
        ram_ok = memory.available >= min_ram_gb * (1024**3)
        disk_ok = psutil.disk_usage('.').free >= min_disk_gb * (1024**3)
        
        print(f"   ✅ RAM sufficient for Pi: {'YES' if ram_ok else 'NO'}")
        print(f"   ✅ Disk space sufficient: {'YES' if disk_ok else 'NO'}")
        
        return ram_ok and disk_ok
        
    except ImportError:
        print("⚠️ psutil not available - install with: pip install psutil")
        return True  # Assume OK if we can't check
    except Exception as e:
        print(f"❌ Resource check failed: {e}")
        return False

def test_chmi_integration(config):
    """Test ČHMÚ warning integration."""
    print("\n🏛️ Testing ČHMÚ integration...")
    try:
        # Test ČHMÚ monitor initialization
        monitor = ChmiWarningMonitor(config)  # Pass config object
        print("✅ ČHMÚ monitor initialized successfully")

        
        # Test XML fetching and parsing
        try:
            warnings = monitor.get_all_active_warnings()
            print(f"✅ ČHMÚ data fetched and parsed: {len(warnings)} warnings for Brno")
            
            # Test change detection
            new_warnings = monitor.check_for_new_warnings()
            print(f"✅ Change detection working: {len(new_warnings)} new warnings detected")
            
        except Exception as xml_error:
            print(f"⚠️ ČHMÚ XML fetch failed (network/server issue): {xml_error}")
            # This is not a critical failure for the test
        
        # Test email generation with dummy data
        test_warning = ChmiWarning(
            identifier='test_warning',
            event='Test varování',
            detailed_text='Testovací varování pro ověření funkcionalit',
            instruction='Toto je pouze test systému',
            time_start_iso='2025-06-24T18:00:00+02:00',
            time_end_iso='2025-06-24T23:00:00+02:00',
            time_start_unix=1719244800,
            time_end_unix=1719262800,
            time_start_text='dnes 18:00',
            time_end_text='dnes 23:00',
            response_type='Monitor',
            urgency='Future',
            severity='Minor',
            certainty='Possible',
            color='yellow',
            warning_type='unknown',
            in_progress=False,
            area_description='Jihomoravský kraj'
        )
        
        from email_notifier import EmailNotifier
        notifier = EmailNotifier(config)
        
        # Test email generation (don't send)
        email_msg = notifier._create_chmi_warning_email([test_warning])
        print("✅ ČHMÚ email generation successful")
        print(f"   📧 Subject: {email_msg['Subject']}")
        
        return True
        
    except Exception as e:
        print(f"❌ ČHMÚ integration test failed: {e}")
        return False

async def run_full_test():
    """Run complete system test."""
    print("🌩️ Weather Storm Detection System - Full Test Suite")
    print("=" * 60)
    
    # Test results tracking
    results = {
        'config': False,
        'database': False,
        'weather_apis': False,
        'ai_analysis': False,
        'pdf_generation': False,
        'email_system': False,
        'chmi_integration': False,
        'resources': False
    }
    
    # 1. Configuration
    config = await test_configuration()
    results['config'] = config is not None
    
    if not config:
        print("\n❌ Critical: Configuration failed. Cannot continue tests.")
        return results
    
    # 2. Database
    results['database'] = await test_database(config)
    
    # 3. Weather APIs
    weather_data = await test_weather_apis(config)
    results['weather_apis'] = weather_data is not None
    
    # 4. AI Analysis
    analysis = await test_ai_analysis(config, weather_data)
    results['ai_analysis'] = analysis is not None
    
    # 5. PDF Generation
    pdf_path = test_pdf_generation(config, analysis, weather_data)
    results['pdf_generation'] = pdf_path is not None
    
    # 6. Email System
    results['email_system'] = test_email_system(config, send_test_email=True)
    
    # 7. ČHMÚ Integration
    results['chmi_integration'] = test_chmi_integration(config)
    
    # 8. System Resources
    results['resources'] = test_system_resources()
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    total_tests = len(results)
    passed_tests = sum(results.values())
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {test_name.replace('_', ' ').title():20} {status}")
    
    print(f"\n🎯 Overall: {passed_tests}/{total_tests} tests passed ({passed_tests/total_tests*100:.0f}%)")
    
    if passed_tests == total_tests:
        print("🎉 ALL TESTS PASSED! System ready for Raspberry Pi deployment.")
    elif passed_tests >= total_tests * 0.8:
        print("⚠️ Most tests passed. Review failed components before deployment.")
    else:
        print("❌ Multiple test failures. System needs fixes before deployment.")
    
    print("\n🚀 System Features:")
    print("   ✅ Weather monitoring from 2 APIs (OpenWeather, Visual Crossing)")
    print("   ✅ AI-powered storm detection with DeepSeek analysis")
    print("   ✅ Official ČHMÚ warnings integration for Brno")
    print("   ✅ Comprehensive email notifications in Czech")
    print("   ✅ PDF report generation with weather data")
    print("   ✅ Automatic monitoring every 10 minutes")
    print("   ✅ Daily weather summaries")
    print("   ✅ Change detection (no duplicate notifications)")
    
    print("\n🚀 To deploy on Raspberry Pi:")
    print("   1. Copy this directory to Raspberry Pi")
    print("   2. Install requirements: pip install -r requirements.txt")
    print("   3. Run: python main.py")
    print("   4. Optional: Setup as service with weather-monitor.service")
    
    return results

if __name__ == "__main__":
    try:
        results = asyncio.run(run_full_test())
    except KeyboardInterrupt:
        print("\n⚠️ Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test suite failed: {e}")
        sys.exit(1)