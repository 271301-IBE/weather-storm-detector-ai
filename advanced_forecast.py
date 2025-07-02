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
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from scipy import interpolate, optimize
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor
import warnings
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
            'primary_method': self.primary_method.value,
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
        # Simple sinusoidal model for daily temperature variation
        # Peak around 14:00, minimum around 06:00
        peak_hour = 14
        min_hour = 6
        
        # Daily temperature range (varies by season)
        daily_range = 8.0 * season_factor  # Base range of 8°C
        
        # Calculate phase in daily cycle
        if hour >= min_hour and hour <= peak_hour:
            # Morning/afternoon warming
            phase = (hour - min_hour) / (peak_hour - min_hour) * np.pi
            temp_offset = daily_range * 0.5 * (np.sin(phase - np.pi/2) + 1)
        else:
            # Evening/night cooling
            if hour > peak_hour:
                hours_since_peak = hour - peak_hour
            else:
                hours_since_peak = hour + 24 - peak_hour
            
            cooling_period = 24 - (peak_hour - min_hour)
            phase = hours_since_peak / cooling_period * np.pi
            temp_offset = daily_range * 0.5 * (1 - np.sin(phase))
        
        return current_temp + temp_offset - daily_range * 0.25  # Adjust baseline
    
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
        self.scaler = StandardScaler()
    
    def polynomial_trend(self, data_points: List[float], timestamps: List[datetime], 
                        future_time: datetime, degree: int = 2) -> Tuple[float, float]:
        """Fit polynomial trend and predict future value with confidence."""
        if len(data_points) < degree + 1:
            return data_points[-1] if data_points else 0.0, 0.1
        
        # Convert timestamps to hours from first timestamp
        time_hours = [(t - timestamps[0]).total_seconds() / 3600 for t in timestamps]
        future_hours = (future_time - timestamps[0]).total_seconds() / 3600
        
        try:
            # Fit polynomial
            coeffs = np.polyfit(time_hours, data_points, degree)
            poly_func = np.poly1d(coeffs)
            
            # Predict future value
            predicted_value = poly_func(future_hours)
            
            # Calculate confidence based on fit quality
            predicted_current = [poly_func(t) for t in time_hours]
            mse = np.mean([(actual - pred)**2 for actual, pred in zip(data_points, predicted_current)])
            confidence = max(0.1, 1.0 - mse / np.var(data_points)) if np.var(data_points) > 0 else 0.1
            
            return float(predicted_value), min(1.0, confidence)
            
        except (np.linalg.LinAlgError, np.RankWarning):
            # Fallback to linear trend
            return self.linear_trend(data_points, timestamps, future_time)
    
    def linear_trend(self, data_points: List[float], timestamps: List[datetime], 
                    future_time: datetime) -> Tuple[float, float]:
        """Simple linear trend analysis."""
        if len(data_points) < 2:
            return data_points[-1] if data_points else 0.0, 0.1
        
        time_hours = [(t - timestamps[0]).total_seconds() / 3600 for t in timestamps]
        future_hours = (future_time - timestamps[0]).total_seconds() / 3600
        
        # Linear regression
        slope, intercept = np.polyfit(time_hours, data_points, 1)
        predicted_value = slope * future_hours + intercept
        
        # R-squared for confidence
        y_mean = np.mean(data_points)
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
        recent_variance = np.var(data_points[-5:]) if len(data_points) >= 5 else np.var(data_points)
        confidence = max(0.1, 1.0 - (recent_variance / (np.var(data_points) + 1e-6)))
        
        return float(predicted), confidence

class MachineLearningPredictor:
    """Machine learning based weather prediction."""
    
    def __init__(self):
        self.models = {}
        self.feature_scalers = {}
        self.is_trained = False
    
    def extract_features(self, weather_data: List[WeatherData], target_hour: int) -> np.ndarray:
        """Extract features for ML prediction."""
        if not weather_data:
            return np.array([])
        
        # Sort by timestamp
        sorted_data = sorted(weather_data, key=lambda x: x.timestamp)
        
        features = []
        
        # Current conditions
        latest = sorted_data[-1]
        features.extend([
            latest.temperature, latest.humidity, latest.pressure,
            latest.wind_speed, latest.wind_direction, latest.precipitation,
            latest.cloud_cover, latest.visibility or 10.0
        ])
        
        # Temporal features
        current_time = datetime.now()
        features.extend([
            current_time.hour, current_time.month, 
            target_hour,  # Hour we're predicting for
            (target_hour - current_time.hour) % 24  # Hours ahead
        ])
        
        # Trend features (if enough data)
        if len(sorted_data) >= 3:
            temp_trend = sorted_data[-1].temperature - sorted_data[-3].temperature
            pressure_trend = sorted_data[-1].pressure - sorted_data[-3].pressure
            humidity_trend = sorted_data[-1].humidity - sorted_data[-3].humidity
        else:
            temp_trend = pressure_trend = humidity_trend = 0.0
        
        features.extend([temp_trend, pressure_trend, humidity_trend])
        
        # Statistical features from recent data
        if len(sorted_data) >= 6:
            recent_temps = [d.temperature for d in sorted_data[-6:]]
            recent_pressures = [d.pressure for d in sorted_data[-6:]]
            
            features.extend([
                np.mean(recent_temps), np.std(recent_temps),
                np.mean(recent_pressures), np.std(recent_pressures),
                max(recent_temps) - min(recent_temps)  # Temperature range
            ])
        else:
            features.extend([latest.temperature, 0, latest.pressure, 0, 0])
        
        return np.array(features).reshape(1, -1)
    
    def train_models(self, historical_data: List[WeatherData]) -> bool:
        """Train ML models on historical data."""
        if len(historical_data) < 50:  # Need minimum data
            logger.warning("Not enough historical data for ML training")
            return False
        
        try:
            # Prepare training data
            X_train = []
            y_train = {'temperature': [], 'humidity': [], 'pressure': []}
            
            # Sort data
            sorted_data = sorted(historical_data, key=lambda x: x.timestamp)
            
            # Create training samples
            for i in range(len(sorted_data) - 6):
                # Use data from position i to i+5 to predict i+6
                features = self.extract_features(sorted_data[i:i+6], sorted_data[i+6].timestamp.hour)
                
                if features.size > 0:
                    X_train.append(features.flatten())
                    y_train['temperature'].append(sorted_data[i+6].temperature)
                    y_train['humidity'].append(sorted_data[i+6].humidity)
                    y_train['pressure'].append(sorted_data[i+6].pressure)
            
            if not X_train:
                return False
            
            X_train = np.array(X_train)
            
            # Train separate models for each variable
            for variable in ['temperature', 'humidity', 'pressure']:
                # Scale features
                self.feature_scalers[variable] = StandardScaler()
                X_scaled = self.feature_scalers[variable].fit_transform(X_train)
                
                # Train Random Forest model
                self.models[variable] = RandomForestRegressor(
                    n_estimators=100, 
                    max_depth=10, 
                    random_state=42,
                    n_jobs=-1
                )
                self.models[variable].fit(X_scaled, y_train[variable])
            
            self.is_trained = True
            logger.info("ML models trained successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error training ML models: {e}")
            return False
    
    def predict(self, weather_data: List[WeatherData], target_time: datetime) -> Tuple[Dict[str, float], float]:
        """Make ML prediction for target time."""
        if not self.is_trained:
            return {}, 0.0
        
        try:
            features = self.extract_features(weather_data, target_time.hour)
            
            if features.size == 0:
                return {}, 0.0
            
            predictions = {}
            confidences = []
            
            for variable in ['temperature', 'humidity', 'pressure']:
                if variable in self.models and variable in self.feature_scalers:
                    X_scaled = self.feature_scalers[variable].transform(features)
                    pred = self.models[variable].predict(X_scaled)[0]
                    predictions[variable] = float(pred)
                    
                    # Confidence based on feature importance and model score
                    confidence = min(1.0, self.models[variable].score(X_scaled, [pred]) if hasattr(self.models[variable], 'score') else 0.7)
                    confidences.append(confidence)
            
            avg_confidence = np.mean(confidences) if confidences else 0.0
            return predictions, avg_confidence
            
        except Exception as e:
            logger.error(f"Error making ML prediction: {e}")
            return {}, 0.0

class AdvancedForecastGenerator:
    """Main class for advanced weather forecasting."""
    
    def __init__(self, config: Config):
        self.config = config
        self.physics_model = AtmosphericPhysicsModel()
        self.trend_analyzer = AdvancedTrendAnalyzer()
        self.ml_predictor = MachineLearningPredictor()
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
        """Clamp weather values to realistic ranges."""
        clamped = {}
        
        # Temperature: -50°C to 50°C
        clamped['temperature'] = max(-50.0, min(50.0, kwargs.get('temperature', 20.0)))
        
        # Humidity: 0% to 100%
        clamped['humidity'] = max(0.0, min(100.0, kwargs.get('humidity', 50.0)))
        
        # Pressure: 900 to 1100 hPa
        clamped['pressure'] = max(900.0, min(1100.0, kwargs.get('pressure', 1013.25)))
        
        # Wind speed: 0 to 50 m/s
        clamped['wind_speed'] = max(0.0, min(50.0, kwargs.get('wind_speed', 0.0)))
        
        # Wind direction: 0 to 360 degrees
        clamped['wind_direction'] = kwargs.get('wind_direction', 0.0) % 360
        
        # Precipitation: 0 to 100 mm/h
        clamped['precipitation'] = max(0.0, min(100.0, kwargs.get('precipitation', 0.0)))
        
        # Precipitation probability: 0% to 100%
        clamped['precipitation_probability'] = max(0.0, min(100.0, kwargs.get('precipitation_probability', 0.0)))
        
        # Cloud cover: 0% to 100%
        clamped['cloud_cover'] = max(0.0, min(100.0, kwargs.get('cloud_cover', 0.0)))
        
        # Visibility: 0.1 to 50 km
        clamped['visibility'] = max(0.1, min(50.0, kwargs.get('visibility', 10.0)))
        
        return clamped
    
    async def generate_physics_forecast(self, weather_data: List[WeatherData]) -> EnhancedWeatherForecast:
        """Generate forecast using atmospheric physics models."""
        if not weather_data:
            return EnhancedWeatherForecast(
                timestamp=datetime.now(),
                forecast_data=[],
                primary_method=ForecastMethod.LOCAL_PHYSICS,
                method_confidences={'physics': 0.0},
                data_sources=[],
                ensemble_weight=None
            )
        
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
            season_factor = 0.8 + 0.4 * np.cos(2 * np.pi * (datetime.now().month - 1) / 12)
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
        
        overall_confidence = np.mean(confidences) if confidences else 0.0
        
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
            return None
        
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
        
        # Train and use ML if enough historical data
        ml_predictions = {}
        ml_confidence = 0.0
        
        if len(weather_data) > 50:
            if self.ml_predictor.train_models(weather_data):
                # Get ML predictions for each hour
                for hour in range(1, 7):
                    future_time = datetime.now() + timedelta(hours=hour)
                    pred, conf = self.ml_predictor.predict(weather_data, future_time)
                    if pred:
                        ml_predictions[hour] = pred
                        ml_confidence = max(ml_confidence, conf)
        
        # Combine forecasts with weighted ensemble
        ensemble_data = []
        method_weights = {
            'physics': 0.4,
            'ai': 0.5 if ai_forecast else 0.0,
            'ml': 0.1 if ml_predictions else 0.0
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
            ml_pred = ml_predictions.get(hour+1, {})
            
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
            
            if ml_pred:
                ensemble_temp += ml_pred.get('temperature', ensemble_temp) * method_weights['ml']
                ensemble_humidity += ml_pred.get('humidity', ensemble_humidity) * method_weights['ml']
                ensemble_pressure += ml_pred.get('pressure', ensemble_pressure) * method_weights['ml']
                ensemble_confidence += ml_confidence * method_weights['ml']
            
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
            if ml_pred:
                alternatives['ml_temp'] = ml_pred.get('temperature')
            
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
                'ml': ml_confidence,
                'ensemble': np.mean([d.metadata.confidence for d in ensemble_data]) if ensemble_data else 0
            },
            data_sources=list(set([d.source for d in weather_data])),
            ensemble_weight=method_weights
        )