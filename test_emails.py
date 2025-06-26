#!/usr/bin/env python3
"""Generátor ukázkových emailů pro testování nového systému."""

import os
import sys
from datetime import datetime, timedelta
from typing import List

# Add project root to path
sys.path.insert(0, '/home/pi/weather-storm-detector')

from models import StormAnalysis, WeatherData, AlertLevel, WeatherCondition
from chmi_warnings import ChmiWarning
from email_notifier import EmailNotifier
from config import load_config

def create_sample_weather_data() -> List[WeatherData]:
    """Vytvořit ukázková meteorologická data."""
    return [
        WeatherData(
            timestamp=datetime.now(),
            source="openweather",
            temperature=18.5,
            humidity=85,
            pressure=1008,
            wind_speed=12.3,
            wind_direction=230,
            precipitation=3.2,
            precipitation_probability=85,
            condition=WeatherCondition.THUNDERSTORM,
            visibility=8.5,
            cloud_cover=90,
            uv_index=3,
            description="Silné bouřky s přívalovým deštěm",
            raw_data={"test": "data"}
        )
    ]

def create_sample_storm_analysis(level: AlertLevel) -> StormAnalysis:
    """Vytvořit ukázkovou AI analýzu bouře."""
    return StormAnalysis(
        timestamp=datetime.now(),
        confidence_score=0.89,
        storm_detected=True,
        alert_level=level,
        predicted_arrival=datetime.now() + timedelta(minutes=45),
        predicted_intensity="heavy",
        analysis_summary="Detekována vysoká pravděpodobnost vzniku silných bouří nad Brnem. Kombinace nízkého tlaku (1008 hPa), vysoké vlhkosti (85%) a silného větru (12.3 m/s) vytváří ideální podmínky pro bouřkovou činnost.",
        recommendations=[
            "Zůstaňte uvnitř budov",
            "Neparkujte pod stromy",
            "Sledujte aktuální radar ČHMÚ",
            "Připravte si svítilnu pro případ výpadku elektřiny"
        ],
        data_quality_score=0.95
    )

def create_sample_chmi_warnings() -> List[ChmiWarning]:
    """Vytvořit ukázková ČHMÚ varování."""
    return [
        ChmiWarning(
            identifier="CHMI_STORM_001",
            event="Velmi silné bouřky",
            warning_type="thunderstorm",
            color="orange",
            urgency="immediate",
            severity="severe",
            certainty="likely",
            response_type="prepare",
            area_description="Jihomoravský kraj - okres Brno-město",
            time_start_unix=int(datetime.now().timestamp()),
            time_end_unix=int((datetime.now() + timedelta(hours=6)).timestamp()),
            time_start_text="dnes 14:00",
            time_end_text="dnes 20:00",
            time_start_iso=datetime.now().isoformat(),
            time_end_iso=(datetime.now() + timedelta(hours=6)).isoformat(),
            detailed_text="Očekávají se velmi silné bouřky s přívalovým deštěm do 40 mm za hodinu, nárazy větru až 90 km/h a možný výskyt krup.",
            instruction="Zůstaňte uvnitř, neparkujte pod stromy, sledujte meteorologický radar.",
            in_progress=True
        ),
        ChmiWarning(
            identifier="CHMI_RAIN_002", 
            event="Vydatný déšť",
            warning_type="rain",
            color="yellow",
            urgency="future",
            severity="moderate",
            certainty="possible",
            response_type="monitor",
            area_description="Jihomoravský kraj",
            time_start_unix=int((datetime.now() + timedelta(hours=2)).timestamp()),
            time_end_unix=int((datetime.now() + timedelta(hours=12)).timestamp()),
            time_start_text="dnes 16:00",
            time_end_text="zítra 02:00",
            time_start_iso=(datetime.now() + timedelta(hours=2)).isoformat(),
            time_end_iso=(datetime.now() + timedelta(hours=12)).isoformat(),
            detailed_text="Očekává se vydatný déšť s úhrny 20-30 mm.",
            instruction="Sledujte aktuální situaci, očekávejte komplikace v dopravě.",
            in_progress=False
        )
    ]

def generate_sample_emails():
    """Vygenerovat ukázkové emaily."""
    print("🔧 Generuji ukázkové emaily...")
    
    try:
        # Load config (může selhat, ale to nevadí pro ukázku)
        try:
            config = load_config()
        except:
            # Fallback config pro ukázku
            class MockConfig:
                class EmailConfig:
                    sender_name = "Clipron AI Weather"
                    sender_email = "weather@example.com"
                    recipient_email = "user@example.com"
                class WeatherConfig:
                    city_name = "Brno"
                    region = "Jihomoravský kraj"
                
                email = EmailConfig()
                weather = WeatherConfig()
            
            config = MockConfig()
        
        notifier = EmailNotifier(config)
        weather_data = create_sample_weather_data()
        chmi_warnings = create_sample_chmi_warnings()
        
        # Create output directory
        os.makedirs('/home/pi/weather-storm-detector/sample_emails', exist_ok=True)
        
        print("\n📧 UKÁZKOVÉ EMAILY:")
        print("=" * 50)
        
        # 1. HIGH Storm Alert Email
        print("\n1️⃣ STORM ALERT - HIGH LEVEL")
        high_analysis = create_sample_storm_analysis(AlertLevel.HIGH)
        msg = notifier._create_storm_alert_email(high_analysis, weather_data)
        
        with open('/home/pi/weather-storm-detector/sample_emails/storm_alert_high.html', 'w', encoding='utf-8') as f:
            f.write(str(msg.get_payload()[0]))
        
        print(f"📧 Subject: {msg['Subject']}")
        print(f"📧 From: {msg['From']}")
        print(f"📧 To: {msg['To']}")
        print("📄 Obsah uložen do: sample_emails/storm_alert_high.html")
        
        # 2. CRITICAL Storm Alert Email  
        print("\n2️⃣ STORM ALERT - CRITICAL LEVEL")
        critical_analysis = create_sample_storm_analysis(AlertLevel.CRITICAL)
        msg = notifier._create_storm_alert_email(critical_analysis, weather_data)
        
        with open('/home/pi/weather-storm-detector/sample_emails/storm_alert_critical.html', 'w', encoding='utf-8') as f:
            f.write(str(msg.get_payload()[0]))
        
        print(f"📧 Subject: {msg['Subject']}")
        print(f"📧 From: {msg['From']}")
        print(f"📧 To: {msg['To']}")
        print("📄 Obsah uložen do: sample_emails/storm_alert_critical.html")
        
        # 3. ČHMÚ Warning Email
        print("\n3️⃣ ČHMÚ WARNING EMAIL")
        msg = notifier._create_chmi_warning_email(chmi_warnings)
        
        with open('/home/pi/weather-storm-detector/sample_emails/chmi_warning.html', 'w', encoding='utf-8') as f:
            f.write(str(msg.get_payload()[0]))
        
        print(f"📧 Subject: {msg['Subject']}")
        print(f"📧 From: {msg['From']}")
        print(f"📧 To: {msg['To']}")
        print("📄 Obsah uložen do: sample_emails/chmi_warning.html")
        
        # 4. Test filtering - MEDIUM level (should be skipped)
        print("\n4️⃣ TEST FILTERING - MEDIUM LEVEL (SHOULD BE SKIPPED)")
        medium_analysis = create_sample_storm_analysis(AlertLevel.MEDIUM)
        notification = notifier.send_storm_alert(medium_analysis, weather_data)
        
        print(f"✅ Result: {notification.message_type}")
        print(f"✅ Sent: {notification.sent_successfully}")
        print(f"✅ Reason: {notification.error_message}")
        
        print("\n" + "=" * 50)
        print("✅ UKÁZKOVÉ EMAILY VYGENEROVÁNY!")
        print("📁 Soubory jsou v: /home/pi/weather-storm-detector/sample_emails/")
        print("📧 Systém posílá pouze HIGH/CRITICAL storm alerts")
        print("📧 ČHMÚ emaily jen pro bouřky/srážky/extrémní výstrahy")
        print("📧 Denní emaily jsou vypnuté")
        
    except Exception as e:
        print(f"❌ Chyba při generování ukázek: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    generate_sample_emails()