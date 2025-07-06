"""Configuration management for weather storm detector."""

import os
from dataclasses import dataclass
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

@dataclass
class WeatherConfig:
    """Weather API configuration."""
    openweather_api_key: str
    visual_crossing_api_key: str
    tomorrow_io_api_key: str
    latitude: float
    longitude: float
    city_name: str
    region: str
    api_retry_attempts: int

@dataclass
class AIConfig:
    """AI analysis configuration."""
    deepseek_api_key: str
    deepseek_api_url: str
    storm_confidence_threshold: float

@dataclass
class EmailConfig:
    """Email notification configuration."""
    smtp_server: str
    smtp_port: int
    smtp_use_ssl: bool
    sender_email: str
    sender_password: str
    sender_name: str
    recipient_email: str
    email_delay_minutes: int

@dataclass
class ChmiConfig:
    """CHMI warning configuration."""
    region_code: str
    xml_url: str

@dataclass
class WebAppConfig:
    """Web application configuration."""
    username: str
    password: str
    secret_key: str

@dataclass
class WebNotificationConfig:
    """Web push notification configuration."""
    vapid_private_key: str
    vapid_public_key: str

@dataclass
class PredictionConfig:
    """Thunderstorm prediction configuration."""
    wind_speed_threshold: float
    precipitation_threshold: float

@dataclass
class SystemConfig:
    """System operation configuration."""
    monitoring_interval_minutes: int
    deepseek_forecast_interval_hours: int
    daily_summary_hour: int
    database_path: str
    local_forecast_interval_minutes: int
    ensemble_forecast_interval_minutes: int
    max_cpu_usage_threshold: int

@dataclass
class Config:
    """Main configuration container."""
    weather: WeatherConfig
    ai: AIConfig
    email: EmailConfig
    system: SystemConfig
    chmi: ChmiConfig
    webapp: WebAppConfig
    web_notification: WebNotificationConfig
    prediction: PredictionConfig

def load_config() -> Config:
    """Load configuration from environment variables."""
    return Config(
        weather=WeatherConfig(
            openweather_api_key=os.getenv("OPENWEATHER_API_KEY"),
            visual_crossing_api_key=os.getenv("VISUAL_CROSSING_API_KEY"),
            tomorrow_io_api_key=os.getenv("TOMORROW_IO_API_KEY"),
            latitude=float(os.getenv("LATITUDE", "49.2384")),
            longitude=float(os.getenv("LONGITUDE", "16.6073")),
            city_name=os.getenv("CITY_NAME", "Brno"),
            region=os.getenv("REGION", "South Moravia"),
            api_retry_attempts=int(os.getenv("API_RETRY_ATTEMPTS", "3"))
        ),
        ai=AIConfig(
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY"),
            deepseek_api_url=os.getenv("DEEPSEEK_API_URL"),
            storm_confidence_threshold=float(os.getenv("STORM_CONFIDENCE_THRESHOLD", "0.99"))
        ),
        email=EmailConfig(
            smtp_server=os.getenv("SMTP_SERVER", "smtp.seznam.cz"),
            smtp_port=int(os.getenv("SMTP_PORT", "465")),
            smtp_use_ssl=os.getenv("SMTP_USE_SSL", "true").lower() == "true",
            sender_email=os.getenv("SENDER_EMAIL"),
            sender_password=os.getenv("SENDER_PASSWORD"),
            sender_name=os.getenv("SENDER_NAME", "Clipron AI"),
            recipient_email=os.getenv("RECIPIENT_EMAIL"),
            email_delay_minutes=int(os.getenv("EMAIL_DELAY_MINUTES", "30"))
        ),
        system=SystemConfig(
            monitoring_interval_minutes=int(os.getenv("MONITORING_INTERVAL_MINUTES", "15")),
            deepseek_forecast_interval_hours=int(os.getenv("DEEPSEEK_FORECAST_INTERVAL_HOURS", "8")),
            daily_summary_hour=int(os.getenv("DAILY_SUMMARY_HOUR", "9")),
            database_path=os.getenv("DATABASE_PATH", "./weather_data.db"),
            local_forecast_interval_minutes=int(os.getenv("LOCAL_FORECAST_INTERVAL_MINUTES", "10")),
            ensemble_forecast_interval_minutes=int(os.getenv("ENSEMBLE_FORECAST_INTERVAL_MINUTES", "30")),
            max_cpu_usage_threshold=int(os.getenv("MAX_CPU_USAGE_THRESHOLD", "60"))
        ),
        chmi=ChmiConfig(
            region_code=os.getenv("CHMI_REGION_CODE", "6203"),
            xml_url=os.getenv("CHMI_XML_URL", "https://www.chmi.cz/files/portal/docs/meteo/om/bulletiny/XOCZ50_OKPR.xml")
        ),
        webapp=WebAppConfig(
            username=os.getenv("WEBAPP_USERNAME", "pi"),
            password=os.getenv("WEBAPP_PASSWORD", "pica1234"),
            secret_key=os.getenv("WEBAPP_SECRET_KEY", "weather_storm_detector_secret_key_2025")
        ),
        web_notification=WebNotificationConfig(
            vapid_private_key=os.getenv("VAPID_PRIVATE_KEY"),
            vapid_public_key=os.getenv("VAPID_PUBLIC_KEY")
        ),
        prediction=PredictionConfig(
            wind_speed_threshold=float(os.getenv("WIND_SPEED_THRESHOLD", "20.0")),
            precipitation_threshold=float(os.getenv("PRECIPITATION_THRESHOLD", "1.0"))
        )
    )