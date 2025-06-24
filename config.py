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
    latitude: float
    longitude: float
    city_name: str
    region: str

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
class SystemConfig:
    """System operation configuration."""
    monitoring_interval_minutes: int
    daily_summary_hour: int
    database_path: str

@dataclass
class Config:
    """Main configuration container."""
    weather: WeatherConfig
    ai: AIConfig
    email: EmailConfig
    system: SystemConfig

def load_config() -> Config:
    """Load configuration from environment variables."""
    return Config(
        weather=WeatherConfig(
            openweather_api_key=os.getenv("OPENWEATHER_API_KEY"),
            visual_crossing_api_key=os.getenv("VISUAL_CROSSING_API_KEY"),
            latitude=float(os.getenv("LATITUDE", "49.2384")),
            longitude=float(os.getenv("LONGITUDE", "16.6073")),
            city_name=os.getenv("CITY_NAME", "Brno"),
            region=os.getenv("REGION", "South Moravia")
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
            monitoring_interval_minutes=int(os.getenv("MONITORING_INTERVAL_MINUTES", "10")),
            daily_summary_hour=int(os.getenv("DAILY_SUMMARY_HOUR", "9")),
            database_path=os.getenv("DATABASE_PATH", "./weather_data.db")
        )
    )