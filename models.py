"""Data models for weather detection system."""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum

class WeatherCondition(Enum):
    """Weather condition types."""
    CLEAR = "clear"
    CLOUDS = "clouds"
    RAIN = "rain"
    THUNDERSTORM = "thunderstorm"
    SNOW = "snow"
    DRIZZLE = "drizzle"
    MIST = "mist"
    FOG = "fog"

class AlertLevel(Enum):
    """Alert severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class WeatherData:
    """Weather data from APIs."""
    timestamp: datetime
    source: str  # "openweather" or "visual_crossing"
    temperature: float
    humidity: float
    pressure: float
    wind_speed: float
    wind_direction: float
    precipitation: float
    precipitation_probability: float
    condition: WeatherCondition
    visibility: Optional[float]
    cloud_cover: float
    uv_index: Optional[float]
    description: str
    raw_data: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['condition'] = self.condition.value
        return data

@dataclass
class StormAnalysis:
    """AI analysis results for storm detection."""
    timestamp: datetime
    confidence_score: float
    storm_detected: bool
    alert_level: AlertLevel
    predicted_arrival: Optional[datetime]
    predicted_intensity: Optional[str]
    analysis_summary: str
    recommendations: List[str]
    data_quality_score: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['alert_level'] = self.alert_level.value
        if self.predicted_arrival:
            data['predicted_arrival'] = self.predicted_arrival.isoformat()
        return data

@dataclass
class PredictedWeatherData:
    """Predicted weather data for a specific timestamp."""
    timestamp: datetime
    temperature: float
    humidity: float
    pressure: float
    wind_speed: float
    wind_direction: float
    precipitation: float
    precipitation_probability: float
    condition: WeatherCondition
    cloud_cover: float
    visibility: Optional[float]
    description: str

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['condition'] = self.condition.value
        return data

@dataclass
class WeatherForecast:
    """Container for a 6-hour weather forecast."""
    timestamp: datetime # When the forecast was generated
    forecast_data: List[PredictedWeatherData] # List of predictions for each hour

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['forecast_data'] = [item.to_dict() for item in self.forecast_data]
        return data

@dataclass
class EmailNotification:
    """Email notification record."""
    timestamp: datetime
    recipient: str
    subject: str
    message_type: str  # "storm_alert", "daily_summary", "chmi_warning", "combined_weather_alert"
    sent_successfully: bool
    error_message: Optional[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data

@dataclass
class ChmiWarningNotification:
    """ČHMÚ warning notification record."""
    timestamp: datetime
    warning_id: str
    event: str
    color: str
    warning_type: str
    time_start: datetime
    time_end: Optional[datetime]
    recipient: str
    sent_successfully: bool
    error_message: Optional[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['time_start'] = self.time_start.isoformat()
        if self.time_end:
            data['time_end'] = self.time_end.isoformat()
        return data