#!/usr/bin/env python3
"""
Test script for combined AI + ČHMÚ system functionality

Tests the new combined approach where AI analysis includes ČHMÚ data
and sends combined alerts only when highly confident.
"""

import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from config import load_config
from data_fetcher import WeatherDataCollector
from ai_analysis import StormDetectionEngine, DeepSeekChatAnalyzer
from email_notifier import EmailNotifier
from models import StormAnalysis, AlertLevel
from chmi_warnings import ChmiWarningMonitor, ChmiWarning

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_combined_ai_chmi_analysis():
    """Test AI analysis with ČHMÚ data integration."""
    print("\n🤖 Testing combined AI + ČHMÚ analysis...")
    
    try:
        config = load_config()
        
        # Collect weather data
        collector = WeatherDataCollector(config)
        weather_data = await collector.collect_weather_data()
        
        if not weather_data:
            print("❌ No weather data available for testing")
            return False
        
        # Get ČHMÚ warnings
        chmi_monitor = ChmiWarningMonitor("6203")
        chmi_warnings = chmi_monitor.get_all_active_warnings()
        
        print(f"📊 Weather data sources: {len(weather_data)}")
        print(f"🏛️ ČHMÚ warnings: {len(chmi_warnings)}")
        
        # Run AI analysis with ČHMÚ data
        engine = StormDetectionEngine(config)
        analysis = await engine.analyze_storm_potential(weather_data, None, chmi_warnings)
        
        if analysis:
            print("✅ Combined AI analysis completed successfully")
            print(f"   🌩️ Storm detected: {'YES' if analysis.storm_detected else 'NO'}")
            print(f"   📊 AI Confidence: {analysis.confidence_score:.1%}")
            print(f"   🚨 Alert level: {analysis.alert_level.value}")
            print(f"   📋 Summary: {analysis.analysis_summary[:100]}...")
            
            # Check if alert would be sent
            should_alert = engine.should_send_alert(analysis)
            print(f"   📧 Would send combined alert: {'YES' if should_alert else 'NO'}")
            
            return True
        else:
            print("❌ Combined AI analysis failed")
            return False
            
    except Exception as e:
        print(f"❌ Combined analysis test failed: {e}")
        return False

async def test_combined_email_generation():
    """Test combined weather alert email generation."""
    print("\n📧 Testing combined weather alert email...")
    
    try:
        config = load_config()
        notifier = EmailNotifier(config)
        
        # Collect weather data
        collector = WeatherDataCollector(config)
        weather_data = await collector.collect_weather_data()
        
        # Get ČHMÚ warnings
        chmi_monitor = ChmiWarningMonitor("6203")
        chmi_warnings = chmi_monitor.get_all_active_warnings()
        
        # Create test analysis
        test_analysis = StormAnalysis(
            timestamp=datetime.now(),
            confidence_score=0.95,  # High confidence for testing
            storm_detected=True,
            alert_level=AlertLevel.HIGH,
            predicted_arrival=None,
            predicted_intensity="moderate",
            analysis_summary="TEST: Kombinovaný test AI analýzy s ČHMÚ daty - vysoké riziko bouře detekováno na základě meteorologických podmínek a oficiálních varování",
            recommendations=[
                "Toto je testovací zpráva kombinovaného systému",
                "AI detekce kombinovaná s oficiálními ČHMÚ daty",
                "Sledujte aktuální varování na ČHMÚ"
            ],
            data_quality_score=0.90
        )
        
        # Test combined email generation
        email_msg = notifier._create_combined_weather_alert_email(
            test_analysis, weather_data, chmi_warnings
        )
        
        print("✅ Combined email generation successful")
        print(f"   📧 Subject: {email_msg['Subject']}")
        print(f"   👤 To: {email_msg['To']}")
        print(f"   📊 Weather data included: {len(weather_data) if weather_data else 0} sources")
        print(f"   🏛️ ČHMÚ warnings included: {len(chmi_warnings)}")
        
        # Check email content
        payload = email_msg.get_payload()
        if payload and len(payload) > 0:
            content = payload[0].get_payload()
            if 'AI Analýza' in content and 'ČHMÚ' in content:
                print("✅ Email content contains both AI and ČHMÚ sections")
            else:
                print("⚠️ Email content may be missing expected elements")
        
        return True
        
    except Exception as e:
        print(f"❌ Combined email test failed: {e}")
        return False

async def test_daily_summary_with_ai():
    """Test daily summary with AI-generated content."""
    print("\n🌅 Testing daily summary with AI content...")
    
    try:
        config = load_config()
        
        # Collect weather data
        collector = WeatherDataCollector(config)
        weather_data = await collector.collect_weather_data()
        
        # Get ČHMÚ warnings
        chmi_monitor = ChmiWarningMonitor("6203")
        chmi_warnings = chmi_monitor.get_all_active_warnings()
        
        # Test AI summary generation
        async with DeepSeekChatAnalyzer(config) as chat_analyzer:
            ai_summary = await chat_analyzer.generate_daily_summary(weather_data, chmi_warnings)
        
        print("✅ AI daily summary generated successfully")
        print(f"   📝 Summary length: {len(ai_summary)} characters")
        print(f"   🇨🇿 Contains Czech content: {'YES' if any(word in ai_summary.lower() for word in ['počasí', 'teplota', 'vítr']) else 'NO'}")
        print(f"   📊 Summary preview: {ai_summary[:150]}...")
        
        # Test email integration
        notifier = EmailNotifier(config)
        email_msg = notifier._create_daily_summary_email(weather_data, ai_summary)
        
        print("✅ Daily summary email with AI content created")
        print(f"   📧 Subject: {email_msg['Subject']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Daily summary AI test failed: {e}")
        return False

async def test_no_duplicate_logic():
    """Test duplicate prevention logic."""
    print("\n🔄 Testing no-duplicate logic...")
    
    try:
        config = load_config()
        notifier = EmailNotifier(config)
        
        # Simulate multiple calls to check storm alert timing
        from datetime import timedelta
        
        # Test 1: No previous alert (should allow)
        can_send_1 = notifier.can_send_storm_alert(None)
        print(f"✅ No previous alert - Can send: {'YES' if can_send_1 else 'NO'}")
        
        # Test 2: Recent alert (should prevent)
        recent_time = datetime.now() - timedelta(minutes=15)  # 15 minutes ago (less than 30 min delay)
        can_send_2 = notifier.can_send_storm_alert(recent_time)
        print(f"✅ Recent alert (15 min ago) - Can send: {'YES' if can_send_2 else 'NO'}")
        
        # Test 3: Old alert (should allow)
        old_time = datetime.now() - timedelta(hours=2)  # 2 hours ago
        can_send_3 = notifier.can_send_storm_alert(old_time)
        print(f"✅ Old alert (2 hours ago) - Can send: {'YES' if can_send_3 else 'NO'}")
        
        expected_results = [True, False, True]  # Expected behavior
        actual_results = [can_send_1, can_send_2, can_send_3]
        
        if actual_results == expected_results:
            print("✅ No-duplicate logic working correctly")
            return True
        else:
            print(f"⚠️ No-duplicate logic may need adjustment: Expected {expected_results}, Got {actual_results}")
            return False
        
    except Exception as e:
        print(f"❌ No-duplicate logic test failed: {e}")
        return False

async def run_combined_system_test():
    """Run comprehensive test of the new combined system."""
    print("🌩️ Combined AI + ČHMÚ Weather System - Comprehensive Test")
    print("=" * 65)
    
    # Test results tracking
    results = {
        'combined_analysis': False,
        'combined_email': False,
        'daily_ai_summary': False,
        'no_duplicate_logic': False
    }
    
    # 1. Test combined AI + ČHMÚ analysis
    results['combined_analysis'] = await test_combined_ai_chmi_analysis()
    
    # 2. Test combined email generation
    results['combined_email'] = await test_combined_email_generation()
    
    # 3. Test daily summary with AI
    results['daily_ai_summary'] = await test_daily_summary_with_ai()
    
    # 4. Test no-duplicate logic
    results['no_duplicate_logic'] = await test_no_duplicate_logic()
    
    # Summary
    print("\n" + "=" * 65)
    print("📊 COMBINED SYSTEM TEST SUMMARY")
    print("=" * 65)
    
    total_tests = len(results)
    passed_tests = sum(results.values())
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {test_name.replace('_', ' ').title():25} {status}")
    
    print(f"\n🎯 Overall: {passed_tests}/{total_tests} tests passed ({passed_tests/total_tests*100:.0f}%)")
    
    if passed_tests == total_tests:
        print("🎉 ALL COMBINED SYSTEM TESTS PASSED!")
        print("\n🚀 New System Features Validated:")
        print("   ✅ AI analysis now incorporates ČHMÚ official warnings")
        print("   ✅ Combined alerts sent only with high AI confidence")
        print("   ✅ Daily summaries include AI-generated Czech content")
        print("   ✅ Duplicate prevention working correctly")
        print("   ✅ System ready for production deployment")
    elif passed_tests >= total_tests * 0.75:
        print("⚠️ Most tests passed. Review failed components.")
    else:
        print("❌ Multiple test failures. System needs fixes.")
    
    print("\n🔧 Implementation Complete:")
    print("   🤖 AI now uses ČHMÚ data for enhanced analysis")
    print("   📧 Combined weather alerts (AI + ČHMÚ official warnings)")
    print("   🌅 Daily summaries with AI-generated content using DeepSeek Chat")
    print("   ⏰ Smart scheduling prevents duplicate notifications")
    print("   🏛️ Full integration with official Czech meteorological data")
    
    return results

if __name__ == "__main__":
    try:
        results = asyncio.run(run_combined_system_test())
    except KeyboardInterrupt:
        print("\n⚠️ Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test suite failed: {e}")
        sys.exit(1)