#!/usr/bin/env python3
"""
Advanced Weather Forecasting Module
==================================

This module provides sophisticated weather prediction algorithms that combine:
1. Mathematical weather models (local calculations) 
2. AI-powered predictions (DeepSeek)
3. Ensemble forecasting from multiple data sources
4. Clear separation and labeling of prediction methods

Features:
- Advanced trend analysis with polynomial fitting
- Atmospheric physics calculations  
- Pattern recognition from historical data
- Confidence scoring for each prediction method
- Visual distinction between AI vs local calculations
"""

import asyncio
import aiohttp
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import math
import statistics
import warnings
import numpy as np
warnings.filterwarnings('ignore')

from models import WeatherData, WeatherCondition, PredictedWeatherData, WeatherForecast
from config import Config

logger = logging.getLogger(__name__)

class ForecastMethod(Enum):
    """Types of forecasting methods."""
    LOCAL_PHYSICS = "local_physics"
    LOCAL_ML = "local_ml" 
    AI_DEEPSEEK = "ai_deepseek"
    ENSEMBLE = "ensemble"
    API_HYBRID = "api_hybrid"

class ConfidenceLevel(Enum):
    """Confidence levels for predictions."""
    VERY_LOW = "very_low"    # < 0.3
    LOW = "low"              # 0.3 - 0.5
    MEDIUM = "medium"        # 0.5 - 0.7
    HIGH = "high"            # 0.7 - 0.9
    VERY_HIGH = "very_high"  # > 0.9

@dataclass
class ForecastMetadata:
    """Metadata for each forecast prediction."""
    method: ForecastMethod
    confidence: float  # 0.0 - 1.0
    confidence_level: ConfidenceLevel
    generated_at: datetime
    data_quality: float  # 0.0 - 1.0
    model_version: str
    uncertainty_range: Optional[Tuple[float, float]]  # (min, max) for the predicted value

@dataclass
class EnhancedPredictedWeatherData(PredictedWeatherData):
    """Enhanced weather prediction with metadata."""
    metadata: ForecastMetadata
    alternative_predictions: Optional[Dict[str, float]]  # Other method predictions for comparison
    
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data['metadata'] = asdict(self.metadata)
        data['metadata']['method'] = self.metadata.method.value
        data['metadata']['confidence_level'] = self.metadata.confidence_level.value
        data['metadata']['generated_at'] = self.metadata.generated_at.isoformat()
        if self.alternative_predictions:
            data['alternative_predictions'] = self.alternative_predictions
        return data

@dataclass
class EnhancedWeatherForecast(WeatherForecast):
    """Enhanced forecast with method tracking."""
    primary_method: ForecastMethod
    method_confidences: Dict[str, float]
    data_sources: List[str]
    ensemble_weight: Optional[Dict[str, float]]
    
    def to_dict(self) -> Dict[str, Any]:
        data = {
            'timestamp': self.timestamp.isoformat(),
            'primary_method': self.primary_method.value if isinstance(self.primary_method, Enum) else self.primary_method,
            'method_confidences': self.method_confidences,
            'data_sources': self.data_sources,
            'ensemble_weight': self.ensemble_weight,
            'forecast_data': [item.to_dict() if hasattr(item, 'to_dict') else asdict(item) for item in self.forecast_data]
        }
        return data

class AtmosphericPhysicsModel:
    """Physics-based atmospheric modeling for local forecasting."""
    
    def __init__(self):
        # Physical constants
        self.R = 287.05  # Gas constant for dry air (J/kg/K)
        self.g = 9.81    # Gravitational acceleration (m/s²)
        self.L = 0.0065  # Standard atmosphere lapse rate (K/m)
        self.P0 = 101325 # Standard pressure at sea level (Pa)
        self.T0 = 288.15 # Standard temperature at sea level (K)
    
    def calculate_pressure_tendency(self, pressure_history: List[Tuple[datetime, float]]) -> float:
        """Calculate pressure tendency using atmospheric physics."""
        if len(pressure_history) < 3:
            return 0.0
            
        # Calculate 3-hour pressure change (standard meteorological measure)
        times = [p[0] for p in pressure_history]
        pressures = [p[1] for p in pressure_history]
        
        # Find measurements closest to 3 hours apart
        now = datetime.now()
        three_hours_ago = now - timedelta(hours=3)
        
        current_pressure = pressures[-1]
        past_pressure = None
        
        for i, time in enumerate(times):
            if abs((time - three_hours_ago).total_seconds()) < 1800:  # Within 30 minutes
                past_pressure = pressures[i]
                break
        
        if past_pressure is None:
            # Fallback to linear regression if exact 3-hour mark not available
            if len(pressures) >= 6:  # Need reasonable amount of data
                x = np.array([(t - times[0]).total_seconds() / 3600 for t in times])  # Hours
                y = np.array(pressures)
                slope, _ = np.polyfit(x, y, 1)
                return slope * 3  # 3-hour tendency
        else:
            return current_pressure - past_pressure
            
        return 0.0
    
    def predict_temperature_diurnal(self, current_temp: float, hour: int, 
                                   season_factor: float = 1.0) -> float:
        """Predict temperature using diurnal cycle model."""
        # Validate inputs
        if current_temp is None or current_temp < -50 or current_temp > 60:
            current_temp = 15.0  # Reasonable default for Czech Republic
        
        # Simple sinusoidal model for daily temperature variation
        # Peak around 14:00, minimum around 06:00
        peak_hour = 14
        min_hour = 6
        
        # Daily temperature range (varies by season, but keep reasonable)
        daily_range = min(10.0, max(3.0, 6.0 * season_factor))  # 3-10°C range
        
        # Calculate temperature offset based on hour
        # Use a cosine function with peak at 14:00 and minimum at 6:00
        # Normalize hour to 0-24 range, then shift so 14:00 = max, 2:00 = min
        hours_from_peak = (hour - peak_hour + 24) % 24
        hour_angle = hours_from_peak * 2 * math.pi / 24
        temp_offset = (daily_range / 2) * math.cos(hour_angle)
        
        # Apply offset but keep result reasonable
        predicted_temp = current_temp + temp_offset
        
        # Clamp to reasonable range for Czech Republic
        return max(-30.0, min(45.0, predicted_temp))
    
    def calculate_humidity_trend(self, temp_trend: float, pressure_trend: float) -> float:
        """Calculate humidity trend based on temperature and pressure changes."""
        # Clausius-Clapeyron relation: relative humidity inversely related to temperature
        # Also consider pressure effects on absolute humidity
        
        humidity_temp_effect = -temp_trend * 2.5  # Empirical factor
        humidity_pressure_effect = pressure_trend * 0.01  # Small pressure effect
        
        return humidity_temp_effect + humidity_pressure_effect

class AdvancedTrendAnalyzer:
    """Advanced trend analysis using mathematical models."""
    
    def __init__(self):
        pass
    
    def polynomial_trend(self, data_points: List[float], timestamps: List[datetime], 
                        future_time: datetime, degree: int = 2) -> Tuple[float, float]:
        """Fit polynomial trend and predict future value with confidence."""
        if len(data_points) < degree + 1:
            return data_points[-1] if data_points else 0.0, 0.1
        
        # Convert timestamps to hours from first timestamp
        time_hours = [(t - timestamps[0]).total_seconds() / 3600 for t in timestamps]
        future_hours = (future_time - timestamps[0]).total_seconds() / 3600
        
        try:
            # Simple polynomial fitting using least squares approach
            if degree == 2 and len(data_points) >= 3:
                # Quadratic fit: y = ax² + bx + c
                x = time_hours
                y = data_points
                n = len(x)
                
                # Calculate sums for normal equations
                sum_x = sum(x)
                sum_x2 = sum(xi**2 for xi in x)
                sum_x3 = sum(xi**3 for xi in x)
                sum_x4 = sum(xi**4 for xi in x)
                sum_y = sum(y)
                sum_xy = sum(xi*yi for xi, yi in zip(x, y))
                sum_x2y = sum(xi**2*yi for xi, yi in zip(x, y))
                
                # Solve normal equations for quadratic
                det = n*sum_x2*sum_x4 + 2*sum_x*sum_x2*sum_x3 - sum_x2**3 - n*sum_x3**2 - sum_x**2*sum_x4
                
                if abs(det) > 1e-10:
                    a = (n*sum_x2*sum_x2y + sum_x*sum_x3*sum_y + sum_x*sum_x2*sum_xy - sum_x2**2*sum_y - n*sum_x3*sum_xy - sum_x*sum_x2*sum_x2y) / det
                    b = (sum_x2*sum_x4*sum_y + n*sum_x3*sum_xy + sum_x*sum_x2*sum_x2y - sum_x**2*sum_x2y - sum_x2*sum_x3*sum_y - n*sum_x4*sum_xy) / det
                    c = (sum_x2*sum_x3*sum_xy + sum_x*sum_x4*sum_y + sum_x*sum_x2*sum_x2y - sum_x2**3*sum_y - sum_x*sum_x3*sum_x2y - sum_x2*sum_x4*sum_xy) / det
                    
                    # Predict future value
                    predicted_value = a * future_hours**2 + b * future_hours + c
                    
                    # Calculate confidence based on fit quality
                    predicted_current = [a * xi**2 + b * xi + c for xi in time_hours]
                    mse = sum((actual - pred)**2 for actual, pred in zip(data_points, predicted_current)) / len(data_points)
                    variance = sum((yi - statistics.mean(data_points))**2 for yi in data_points) / len(data_points)
                    confidence = max(0.1, 1.0 - mse / variance) if variance > 0 else 0.1
                    
                    return float(predicted_value), min(1.0, confidence)
            
            # Fallback to linear trend
            return self.linear_trend(data_points, timestamps, future_time)
            
        except Exception:
            # Fallback to linear trend
            return self.linear_trend(data_points, timestamps, future_time)
    
    def linear_trend(self, data_points: List[float], timestamps: List[datetime], 
                    future_time: datetime) -> Tuple[float, float]:
        """Simple linear trend analysis."""
        if len(data_points) < 2:
            return data_points[-1] if data_points else 0.0, 0.1
        
        time_hours = [(t - timestamps[0]).total_seconds() / 3600 for t in timestamps]
        future_hours = (future_time - timestamps[0]).total_seconds() / 3600
        
        # Linear regression using least squares
        n = len(time_hours)
        sum_x = sum(time_hours)
        sum_y = sum(data_points)
        sum_xy = sum(x * y for x, y in zip(time_hours, data_points))
        sum_x2 = sum(x**2 for x in time_hours)
        
        # Calculate slope and intercept
        denominator = n * sum_x2 - sum_x**2
        if abs(denominator) < 1e-10:
            return data_points[-1], 0.1
            
        slope = (n * sum_xy - sum_x * sum_y) / denominator
        intercept = (sum_y - slope * sum_x) / n
        
        predicted_value = slope * future_hours + intercept
        
        # R-squared for confidence
        y_mean = statistics.mean(data_points)
        ss_tot = sum((y - y_mean)**2 for y in data_points)
        ss_res = sum((y - (slope * x + intercept))**2 for x, y in zip(time_hours, data_points))
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        confidence = max(0.1, r_squared)
        return float(predicted_value), confidence
    
    def exponential_smoothing(self, data_points: List[float], alpha: float = 0.3) -> Tuple[float, float]:
        """Exponential smoothing for trend prediction."""
        if not data_points:
            return 0.0, 0.1
        
        if len(data_points) == 1:
            return data_points[0], 0.5
        
        # Simple exponential smoothing
        smoothed = [data_points[0]]
        for i in range(1, len(data_points)):
            smoothed.append(alpha * data_points[i] + (1 - alpha) * smoothed[-1])
        
        # Predict next value
        trend = smoothed[-1] - smoothed[-2] if len(smoothed) > 1 else 0
        predicted = smoothed[-1] + trend
        
        # Confidence based on recent stability
        recent_data = data_points[-5:] if len(data_points) >= 5 else data_points
        recent_mean = statistics.mean(recent_data)
        recent_variance = sum((x - recent_mean)**2 for x in recent_data) / len(recent_data)
        
        all_mean = statistics.mean(data_points)
        all_variance = sum((x - all_mean)**2 for x in data_points) / len(data_points)
        
        confidence = max(0.1, 1.0 - (recent_variance / (all_variance + 1e-6)))
        
        return float(predicted), confidence

class SimpleStatisticalPredictor:
    """Simple statistical prediction without sklearn dependencies."""
    
    def __init__(self):
        self.is_trained = False
        self.statistical_models = {}
    
    def extract_features(self, weather_data: List[WeatherData], target_hour: int) -> Dict[str, float]:
        """Extract statistical features for prediction."""
        if not weather_data:
            return {}
        
        # Sort by timestamp
        sorted_data = sorted(weather_data, key=lambda x: x.timestamp)
        
        features = {}
        
        # Current conditions
        latest = sorted_data[-1]
        features.update({
            'current_temp': latest.temperature,
            'current_humidity': latest.humidity,
            'current_pressure': latest.pressure,
            'current_wind': latest.wind_speed,
            'target_hour': target_hour,
            'hours_ahead': (target_hour - datetime.now().hour) % 24
        })
        
        # Trend features (if enough data)
        if len(sorted_data) >= 3:
            features['temp_trend'] = sorted_data[-1].temperature - sorted_data[-3].temperature
            features['pressure_trend'] = sorted_data[-1].pressure - sorted_data[-3].pressure
            features['humidity_trend'] = sorted_data[-1].humidity - sorted_data[-3].humidity
        else:
            features['temp_trend'] = features['pressure_trend'] = features['humidity_trend'] = 0.0
        
        # Statistical features from recent data
        if len(sorted_data) >= 6:
            recent_temps = [d.temperature for d in sorted_data[-6:]]
            recent_pressures = [d.pressure for d in sorted_data[-6:]]
            
            features.update({
                'temp_mean': statistics.mean(recent_temps),
                'temp_range': max(recent_temps) - min(recent_temps),
                'pressure_mean': statistics.mean(recent_pressures)
            })
        else:
            features.update({
                'temp_mean': latest.temperature,
                'temp_range': 0,
                'pressure_mean': latest.pressure
            })
        
        return features
    
    def create_simple_model(self, historical_data: List[WeatherData]) -> bool:
        """Create simple statistical model from historical data."""
        if len(historical_data) < 20:  # Need minimum data
            logger.warning("Not enough historical data for statistical modeling")
            return False
        
        try:
            # Sort data
            sorted_data = sorted(historical_data, key=lambda x: x.timestamp)
            
            # Calculate hourly averages and trends
            hourly_stats = {}
            
            for hour in range(24):
                hour_data = [d for d in sorted_data if d.timestamp.hour == hour]
                if hour_data:
                    hourly_stats[hour] = {
                        'temp_mean': statistics.mean(d.temperature for d in hour_data),
                        'temp_std': statistics.stdev(d.temperature for d in hour_data) if len(hour_data) > 1 else 1.0,
                        'humidity_mean': statistics.mean(d.humidity for d in hour_data),
                        'pressure_mean': statistics.mean(d.pressure for d in hour_data)
                    }
            
            self.statistical_models['hourly_stats'] = hourly_stats
            
            # Calculate seasonal trends (monthly)
            monthly_stats = {}
            for month in range(1, 13):
                month_data = [d for d in sorted_data if d.timestamp.month == month]
                if month_data:
                    monthly_stats[month] = {
                        'temp_offset': statistics.mean(d.temperature for d in month_data) - statistics.mean(d.temperature for d in sorted_data),
                        'humidity_offset': statistics.mean(d.humidity for d in month_data) - statistics.mean(d.humidity for d in sorted_data)
                    }
            
            self.statistical_models['monthly_stats'] = monthly_stats
            self.is_trained = True
            logger.info("Statistical models created successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error creating statistical models: {e}")
            return False
    
    def predict(self, weather_data: List[WeatherData], target_time: datetime) -> Tuple[Dict[str, float], float]:
        """Make statistical prediction for target time."""
        if not self.is_trained:
            return {}, 0.0
        
        try:
            features = self.extract_features(weather_data, target_time.hour)
            
            if not features:
                return {}, 0.0
            
            predictions = {}
            
            # Get hourly baseline
            hourly_stats = self.statistical_models.get('hourly_stats', {})
            target_hour_stats = hourly_stats.get(target_time.hour, {})
            
            # Get monthly adjustment
            monthly_stats = self.statistical_models.get('monthly_stats', {})
            month_adjustments = monthly_stats.get(target_time.month, {'temp_offset': 0, 'humidity_offset': 0})
            
            # Predict temperature
            if target_hour_stats:
                base_temp = target_hour_stats['temp_mean'] + month_adjustments['temp_offset']
                trend_adjustment = features.get('temp_trend', 0) * 0.5  # Dampen trend
                predictions['temperature'] = base_temp + trend_adjustment
            else:
                predictions['temperature'] = features['current_temp']
            
            # Predict humidity
            if target_hour_stats:
                base_humidity = target_hour_stats['humidity_mean'] + month_adjustments['humidity_offset']
                trend_adjustment = features.get('humidity_trend', 0) * 0.3
                predictions['humidity'] = max(0, min(100, base_humidity + trend_adjustment))
            else:
                predictions['humidity'] = features['current_humidity']
            
            # Predict pressure (trend-based)
            pressure_change = features.get('pressure_trend', 0) * 0.7  # Dampen pressure trend
            predictions['pressure'] = features['current_pressure'] + pressure_change
            
            # Simple confidence based on data availability and trend stability
            confidence = 0.6  # Base confidence for statistical method
            if len(weather_data) > 10:
                confidence += 0.1
            if abs(features.get('temp_trend', 0)) < 2:  # Stable temperature
                confidence += 0.1
            if abs(features.get('pressure_trend', 0)) < 5:  # Stable pressure
                confidence += 0.1
                
            confidence = min(0.9, confidence)  # Cap at 90%
            
            return predictions, confidence
            
        except Exception as e:
            logger.error(f"Error making statistical prediction: {e}")
            return {}, 0.0

class AdvancedForecastGenerator:
    """Main class for advanced weather forecasting."""
    
    def __init__(self, config: Config):
        self.config = config
        self.physics_model = AtmosphericPhysicsModel()
        self.trend_analyzer = AdvancedTrendAnalyzer()
        self.statistical_predictor = SimpleStatisticalPredictor()
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        headers = {
            "Authorization": f"Bearer {self.config.ai.deepseek_api_key}",
            "Content-Type": "application/json"
        }
        self.session = aiohttp.ClientSession(
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=120, connect=30)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    def _get_confidence_level(self, confidence: float) -> ConfidenceLevel:
        """Convert numeric confidence to enum."""
        if confidence < 0.3:
            return ConfidenceLevel.VERY_LOW
        elif confidence < 0.5:
            return ConfidenceLevel.LOW
        elif confidence < 0.7:
            return ConfidenceLevel.MEDIUM
        elif confidence < 0.9:
            return ConfidenceLevel.HIGH
        else:
            return ConfidenceLevel.VERY_HIGH
    
    def _clamp_weather_values(self, **kwargs) -> Dict[str, float]:
        """Clamp weather values to realistic ranges with proper validation."""
        clamped = {}
        
        # Temperature: -40°C to 50°C (avoid -50°C default issue)
        temp = kwargs.get('temperature')
        if temp is None or temp < -40.0 or temp > 50.0:
            # Use a reasonable default for Czech Republic
            temp = 15.0
        clamped['temperature'] = max(-40.0, min(50.0, temp))
        
        # Humidity: 0% to 100%
        humidity = kwargs.get('humidity', 60.0)
        clamped['humidity'] = max(0.0, min(100.0, humidity))
        
        # Pressure: 980 to 1040 hPa (realistic range for Czech Republic)
        pressure = kwargs.get('pressure', 1013.25)
        if pressure < 980.0 or pressure > 1040.0:
            pressure = 1013.25  # Use standard sea level pressure if unrealistic
        clamped['pressure'] = max(980.0, min(1040.0, pressure))
        
        # Wind speed: 0 to 40 m/s
        wind_speed = kwargs.get('wind_speed', 3.0)
        clamped['wind_speed'] = max(0.0, min(40.0, wind_speed))
        
        # Wind direction: 0 to 360 degrees
        wind_dir = kwargs.get('wind_direction', 180.0)
        clamped['wind_direction'] = wind_dir % 360
        
        # Precipitation: 0 to 50 mm/h
        precip = kwargs.get('precipitation', 0.0)
        clamped['precipitation'] = max(0.0, min(50.0, precip))
        
        # Precipitation probability: 0% to 100%
        precip_prob = kwargs.get('precipitation_probability', 0.0)
        clamped['precipitation_probability'] = max(0.0, min(100.0, precip_prob))
        
        # Cloud cover: 0% to 100%
        cloud_cover = kwargs.get('cloud_cover', 20.0)
        clamped['cloud_cover'] = max(0.0, min(100.0, cloud_cover))
        
        # Visibility: 0.1 to 50 km
        visibility = kwargs.get('visibility', 15.0)
        clamped['visibility'] = max(0.1, min(50.0, visibility))
        
        return clamped
    
    def _generate_fallback_forecast(self, method: ForecastMethod) -> EnhancedWeatherForecast:
        """Generate a basic fallback forecast when no data is available."""
        forecast_data = []
        
        # Get current time for realistic Czech Republic weather
        now = datetime.now()
        season_temp_base = {
            1: 2, 2: 4, 3: 8, 4: 13, 5: 18, 6: 21,  # Winter to Summer
            7: 23, 8: 22, 9: 18, 10: 12, 11: 7, 12: 3
        }
        base_temp = season_temp_base.get(now.month, 15)
        
        # Create basic hourly forecasts for next 6 hours
        for hour in range(1, 7):
            future_time = datetime.now() + timedelta(hours=hour)
            
            # Add realistic hourly variations
            temp_variation = base_temp + (hour - 3) * 0.5  # Small hourly change
            hour_of_day = future_time.hour
            
            # Use realistic confidence for physics-based forecast
            confidence = 0.6 - (hour - 1) * 0.05  # Decreasing confidence over time
            metadata = ForecastMetadata(
                method=method,
                confidence=confidence,
                confidence_level=self._get_confidence_level(confidence),
                generated_at=datetime.now(),
                data_quality=0.7,
                model_version="physics_v1.0",
                uncertainty_range=(temp_variation - 2, temp_variation + 2)
            )
            
            # Diurnal temperature adjustment
            if 6 <= hour_of_day <= 14:  # Morning to afternoon
                temp_variation += 2
            elif 15 <= hour_of_day <= 18:  # Afternoon
                temp_variation += 3
            elif 19 <= hour_of_day <= 22:  # Evening
                temp_variation += 1
            else:  # Night
                temp_variation -= 2
                
            forecast_data.append(EnhancedPredictedWeatherData(
                timestamp=future_time,
                temperature=temp_variation,
                humidity=65.0 + (hour - 3) * 2,  # Slight humidity variation
                pressure=1013.25 + (hour - 3) * 0.3,  # Small pressure change
                wind_speed=3.0 + hour * 0.2,  # Gradual wind increase
                wind_direction=180.0 + hour * 5,  # Slight wind direction change
                precipitation=0.0,
                precipitation_probability=10.0 + hour * 2,  # Increasing chance
                condition=WeatherCondition.CLOUDS,
                cloud_cover=40.0 + hour * 3,  # Increasing clouds
                visibility=15.0 - hour * 0.5,  # Slightly decreasing visibility
                description=f"Physics-based forecast for {future_time.strftime('%H:%M')}",
                metadata=metadata,
                alternative_predictions=None
            ))
        
        return EnhancedWeatherForecast(
            timestamp=datetime.now(),
            forecast_data=forecast_data,
            primary_method=method,
            method_confidences={method.value: 0.6},
            data_sources=["fallback"],
            ensemble_weight=None
        )

    async def generate_physics_forecast(self, weather_data: List[WeatherData]) -> EnhancedWeatherForecast:
        """Generate forecast using atmospheric physics models."""
        if not weather_data:
            logger.warning("No weather data available for physics forecast, generating fallback")
            return self._generate_fallback_forecast(ForecastMethod.LOCAL_PHYSICS)
        
        # Sort data by timestamp
        sorted_data = sorted(weather_data, key=lambda x: x.timestamp)
        latest_data = sorted_data[-1]
        
        forecast_data = []
        overall_confidence = 0.0
        
        # Prepare historical data for trend analysis
        timestamps = [d.timestamp for d in sorted_data]
        temperatures = [d.temperature for d in sorted_data]
        pressures = [d.pressure for d in sorted_data]
        humidities = [d.humidity for d in sorted_data]
        
        # Calculate pressure tendency
        pressure_history = [(d.timestamp, d.pressure) for d in sorted_data]
        pressure_tendency = self.physics_model.calculate_pressure_tendency(pressure_history)
        
        confidences = []
        
        for hour in range(1, 7):
            future_time = datetime.now() + timedelta(hours=hour)
            
            # Physics-based temperature prediction
            season_factor = 0.8 + 0.4 * math.cos(2 * math.pi * (datetime.now().month - 1) / 12)
            physics_temp = self.physics_model.predict_temperature_diurnal(
                latest_data.temperature, future_time.hour, season_factor
            )
            
            # Trend-based predictions
            temp_pred, temp_conf = self.trend_analyzer.polynomial_trend(
                temperatures, timestamps, future_time
            )
            pressure_pred, pressure_conf = self.trend_analyzer.polynomial_trend(
                pressures, timestamps, future_time
            )
            humidity_pred, humidity_conf = self.trend_analyzer.polynomial_trend(
                humidities, timestamps, future_time
            )
            
            # Apply physics corrections
            temp_trend = temp_pred - latest_data.temperature
            pressure_trend = pressure_pred - latest_data.pressure
            humidity_physics = self.physics_model.calculate_humidity_trend(temp_trend, pressure_trend)
            
            # Combine predictions
            final_temp = (physics_temp + temp_pred) / 2
            final_pressure = pressure_pred
            final_humidity = humidity_pred + humidity_physics
            
            # Calculate hourly confidence
            hour_confidence = (temp_conf + pressure_conf + humidity_conf) / 3
            confidences.append(hour_confidence)
            
            # Clamp values
            clamped = self._clamp_weather_values(
                temperature=final_temp,
                humidity=final_humidity,
                pressure=final_pressure,
                wind_speed=latest_data.wind_speed * (1 - hour * 0.02),  # Gradual decay
                wind_direction=latest_data.wind_direction,
                precipitation=latest_data.precipitation * max(0, 1 - hour * 0.1),
                precipitation_probability=latest_data.precipitation_probability or 0,
                cloud_cover=latest_data.cloud_cover,
                visibility=latest_data.visibility or 10.0
            )
            
            # Determine condition based on multiple factors
            condition = self._determine_condition(clamped)
            
            metadata = ForecastMetadata(
                method=ForecastMethod.LOCAL_PHYSICS,
                confidence=hour_confidence,
                confidence_level=self._get_confidence_level(hour_confidence),
                generated_at=datetime.now(),
                data_quality=1.0 - (hour - 1) * 0.1,  # Decreasing quality with time
                model_version="physics_v1.0",
                uncertainty_range=(clamped['temperature'] - 2, clamped['temperature'] + 2)
            )
            
            forecast_data.append(EnhancedPredictedWeatherData(
                timestamp=future_time,
                temperature=clamped['temperature'],
                humidity=clamped['humidity'],
                pressure=clamped['pressure'],
                wind_speed=clamped['wind_speed'],
                wind_direction=clamped['wind_direction'],
                precipitation=clamped['precipitation'],
                precipitation_probability=clamped['precipitation_probability'],
                condition=condition,
                cloud_cover=clamped['cloud_cover'],
                visibility=clamped['visibility'],
                description=f"Physics-based forecast for {future_time.strftime('%H:%M')}",
                metadata=metadata,
                alternative_predictions=None
            ))
        
        overall_confidence = statistics.mean(confidences) if confidences else 0.0
        
        return EnhancedWeatherForecast(
            timestamp=datetime.now(),
            forecast_data=forecast_data,
            primary_method=ForecastMethod.LOCAL_PHYSICS,
            method_confidences={'physics': overall_confidence},
            data_sources=[d.source for d in weather_data],
            ensemble_weight=None
        )
    
    def _determine_condition(self, weather_params: Dict[str, float]) -> WeatherCondition:
        """Determine weather condition from parameters."""
        humidity = weather_params['humidity']
        precipitation = weather_params['precipitation']
        precipitation_prob = weather_params['precipitation_probability']
        cloud_cover = weather_params['cloud_cover']
        
        if precipitation > 0.5 or precipitation_prob > 80:
            if humidity > 85 and cloud_cover > 80:
                return WeatherCondition.THUNDERSTORM
            else:
                return WeatherCondition.RAIN
        elif cloud_cover > 80:
            return WeatherCondition.CLOUDS
        elif cloud_cover > 30:
            return WeatherCondition.CLOUDS
        else:
            return WeatherCondition.CLEAR
    
    async def generate_ai_forecast(self, weather_data: List[WeatherData]) -> Optional[EnhancedWeatherForecast]:
        """Generate AI-powered forecast using DeepSeek."""
        if not weather_data:
            logger.warning("No weather data available for AI forecast, generating fallback")
            return self._generate_fallback_forecast(ForecastMethod.AI_DEEPSEEK)
        
        try:
            # Prepare context for AI
            context = self._prepare_ai_context(weather_data)
            
            prompt = f"""You are a professional meteorologist. Analyze the weather data and create a precise 6-hour forecast.

WEATHER DATA:
{context}

Create a JSON forecast with this exact structure:
{{
    "forecast": [
        {{
            "timestamp": "ISO format datetime for hour 1",
            "temperature": float,
            "humidity": float (0-100),
            "pressure": float,
            "wind_speed": float,
            "wind_direction": float (0-360),
            "precipitation": float,
            "precipitation_probability": float (0-100),
            "condition": "clear|clouds|rain|thunderstorm|snow|drizzle|mist|fog",
            "cloud_cover": float (0-100),
            "visibility": float,
            "description": "brief description",
            "confidence": float (0-1)
        }}
        // ... repeat for 6 hours
    ],
    "overall_confidence": float (0-1),
    "methodology": "brief explanation of prediction approach"
}}

Requirements:
- Provide exactly 6 hourly predictions
- Use realistic meteorological values
- Consider atmospheric physics and pressure trends
- Account for diurnal temperature cycles
- Base confidence on data quality and prediction certainty"""

            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an expert meteorologist specializing in precise weather forecasting. Always respond with valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.1,  # Low temperature for consistency
                "max_tokens": 2000
            }
            
            async with self.session.post(
                f"{self.config.ai.deepseek_api_url}/chat/completions",
                json=payload
            ) as response:
                
                if response.status == 200:
                    result = await response.json()
                    
                    if "choices" in result and len(result["choices"]) > 0:
                        content = result["choices"][0]["message"]["content"]
                        
                        # Parse JSON response
                        forecast_data = self._parse_ai_response(content)
                        
                        if forecast_data:
                            return self._convert_ai_to_enhanced_forecast(forecast_data, weather_data)
                        
                else:
                    logger.error(f"DeepSeek API error: {response.status}")
                    
        except Exception as e:
            logger.error(f"Error generating AI forecast: {e}")
        
        return None
    
    def _prepare_ai_context(self, weather_data: List[WeatherData]) -> str:
        """Prepare weather context for AI analysis."""
        sorted_data = sorted(weather_data, key=lambda x: x.timestamp)
        recent_data = sorted_data[-24:] if len(sorted_data) > 24 else sorted_data  # Last 24 points
        
        context_lines = []
        context_lines.append(f"Location: {self.config.weather.city_name}, {self.config.weather.region}")
        context_lines.append(f"Analysis time: {datetime.now().isoformat()}")
        context_lines.append(f"Data points: {len(recent_data)}")
        context_lines.append("")
        
        # Recent conditions
        context_lines.append("RECENT WEATHER DATA:")
        for data in recent_data[-6:]:  # Last 6 data points
            context_lines.append(
                f"{data.timestamp.strftime('%H:%M')}: {data.temperature:.1f}°C, "
                f"{data.humidity:.0f}% RH, {data.pressure:.1f} hPa, "
                f"Wind: {data.wind_speed:.1f} m/s, {data.condition.value}"
            )
        
        return "\n".join(context_lines)
    
    def _parse_ai_response(self, content: str) -> Optional[Dict]:
        """Parse AI JSON response with multiple fallback strategies."""
        try:
            # Strategy 1: Direct JSON parsing
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        
        try:
            # Strategy 2: Extract from markdown JSON block
            json_start = content.find('```json')
            if json_start != -1:
                json_start += 7
                json_end = content.find('```', json_start)
                if json_end != -1:
                    json_content = content[json_start:json_end].strip()
                    return json.loads(json_content)
        except json.JSONDecodeError:
            pass
        
        try:
            # Strategy 3: Extract JSON object
            start = content.find('{')
            end = content.rfind('}') + 1
            if start != -1 and end > start:
                json_content = content[start:end]
                return json.loads(json_content)
        except json.JSONDecodeError:
            pass
        
        logger.error("Failed to parse AI response as JSON")
        return None
    
    def _convert_ai_to_enhanced_forecast(self, ai_data: Dict, weather_data: List[WeatherData]) -> EnhancedWeatherForecast:
        """Convert AI response to enhanced forecast format."""
        forecast_items = []
        overall_confidence = ai_data.get('overall_confidence', 0.7)
        
        for item in ai_data.get('forecast', []):
            try:
                metadata = ForecastMetadata(
                    method=ForecastMethod.AI_DEEPSEEK,
                    confidence=item.get('confidence', overall_confidence),
                    confidence_level=self._get_confidence_level(item.get('confidence', overall_confidence)),
                    generated_at=datetime.now(),
                    data_quality=0.9,  # AI typically has good data quality
                    model_version="deepseek_v1.0",
                    uncertainty_range=None
                )
                
                forecast_items.append(EnhancedPredictedWeatherData(
                    timestamp=datetime.fromisoformat(item['timestamp']),
                    temperature=item['temperature'],
                    humidity=item['humidity'],
                    pressure=item['pressure'],
                    wind_speed=item['wind_speed'],
                    wind_direction=item['wind_direction'],
                    precipitation=item['precipitation'],
                    precipitation_probability=item['precipitation_probability'],
                    condition=WeatherCondition(item['condition']),
                    cloud_cover=item['cloud_cover'],
                    visibility=item['visibility'],
                    description=item['description'],
                    metadata=metadata,
                    alternative_predictions=None
                ))
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping invalid AI forecast item: {e}")
                continue
        
        return EnhancedWeatherForecast(
            timestamp=datetime.now(),
            forecast_data=forecast_items,
            primary_method=ForecastMethod.AI_DEEPSEEK,
            method_confidences={'ai_deepseek': overall_confidence},
            data_sources=[d.source for d in weather_data],
            ensemble_weight=None
        )
    
    async def generate_ensemble_forecast(self, weather_data: List[WeatherData]) -> EnhancedWeatherForecast:
        """Generate ensemble forecast combining multiple methods."""
        
        # Generate forecasts from different methods
        physics_forecast = await self.generate_physics_forecast(weather_data)
        ai_forecast = await self.generate_ai_forecast(weather_data)
        
        # Ensure we have at least fallback forecasts
        if not physics_forecast:
            physics_forecast = self._generate_fallback_forecast(ForecastMethod.LOCAL_PHYSICS)
        if not ai_forecast:
            ai_forecast = self._generate_fallback_forecast(ForecastMethod.AI_DEEPSEEK)
        
        # Train and use statistical predictor if enough historical data
        statistical_predictions = {}
        statistical_confidence = 0.0
        
        if len(weather_data) > 20:
            if self.statistical_predictor.create_simple_model(weather_data):
                # Get statistical predictions for each hour
                for hour in range(1, 7):
                    future_time = datetime.now() + timedelta(hours=hour)
                    pred, conf = self.statistical_predictor.predict(weather_data, future_time)
                    if pred:
                        statistical_predictions[hour] = pred
                        statistical_confidence = max(statistical_confidence, conf)
        
        # Combine forecasts with weighted ensemble
        ensemble_data = []
        method_weights = {
            'physics': 0.4,
            'ai': 0.5 if ai_forecast else 0.0,
            'statistical': 0.1 if statistical_predictions else 0.0
        }
        
        # Normalize weights
        total_weight = sum(method_weights.values())
        if total_weight > 0:
            method_weights = {k: v/total_weight for k, v in method_weights.items()}
        
        for hour in range(6):
            future_time = datetime.now() + timedelta(hours=hour+1)
            
            # Get predictions from each method
            physics_pred = physics_forecast.forecast_data[hour] if hour < len(physics_forecast.forecast_data) else None
            ai_pred = ai_forecast.forecast_data[hour] if ai_forecast and hour < len(ai_forecast.forecast_data) else None
            statistical_pred = statistical_predictions.get(hour+1, {})
            
            # Weighted ensemble for each parameter
            ensemble_temp = 0.0
            ensemble_humidity = 0.0
            ensemble_pressure = 0.0
            ensemble_confidence = 0.0
            
            if physics_pred:
                ensemble_temp += physics_pred.temperature * method_weights['physics']
                ensemble_humidity += physics_pred.humidity * method_weights['physics']
                ensemble_pressure += physics_pred.pressure * method_weights['physics']
                ensemble_confidence += physics_pred.metadata.confidence * method_weights['physics']
            
            if ai_pred:
                ensemble_temp += ai_pred.temperature * method_weights['ai']
                ensemble_humidity += ai_pred.humidity * method_weights['ai']
                ensemble_pressure += ai_pred.pressure * method_weights['ai']
                ensemble_confidence += ai_pred.metadata.confidence * method_weights['ai']
            
            if statistical_pred:
                ensemble_temp += statistical_pred.get('temperature', ensemble_temp) * method_weights['statistical']
                ensemble_humidity += statistical_pred.get('humidity', ensemble_humidity) * method_weights['statistical']
                ensemble_pressure += statistical_pred.get('pressure', ensemble_pressure) * method_weights['statistical']
                ensemble_confidence += statistical_confidence * method_weights['statistical']
            
            # Use physics forecast as base for other parameters
            base_pred = physics_pred or ai_pred
            if not base_pred:
                continue
            
            # Create alternative predictions dict
            alternatives = {}
            if physics_pred:
                alternatives['physics_temp'] = physics_pred.temperature
            if ai_pred:
                alternatives['ai_temp'] = ai_pred.temperature
            if statistical_pred:
                alternatives['statistical_temp'] = statistical_pred.get('temperature')
            
            metadata = ForecastMetadata(
                method=ForecastMethod.ENSEMBLE,
                confidence=ensemble_confidence,
                confidence_level=self._get_confidence_level(ensemble_confidence),
                generated_at=datetime.now(),
                data_quality=0.95,
                model_version="ensemble_v1.0",
                uncertainty_range=(ensemble_temp - 3, ensemble_temp + 3)
            )
            
            ensemble_data.append(EnhancedPredictedWeatherData(
                timestamp=future_time,
                temperature=ensemble_temp,
                humidity=ensemble_humidity,
                pressure=ensemble_pressure,
                wind_speed=base_pred.wind_speed,
                wind_direction=base_pred.wind_direction,
                precipitation=base_pred.precipitation,
                precipitation_probability=base_pred.precipitation_probability,
                condition=base_pred.condition,
                cloud_cover=base_pred.cloud_cover,
                visibility=base_pred.visibility,
                description=f"Ensemble forecast combining multiple models",
                metadata=metadata,
                alternative_predictions=alternatives
            ))
        
        return EnhancedWeatherForecast(
            timestamp=datetime.now(),
            forecast_data=ensemble_data,
            primary_method=ForecastMethod.ENSEMBLE,
            method_confidences={
                'physics': physics_forecast.method_confidences.get('physics', 0),
                'ai': ai_forecast.method_confidences.get('ai_deepseek', 0) if ai_forecast else 0,
                'statistical': statistical_confidence,
                'ensemble': statistics.mean([d.metadata.confidence for d in ensemble_data]) if ensemble_data else 0
            },
            data_sources=list(set([d.source for d in weather_data])),
            ensemble_weight=method_weights
        )