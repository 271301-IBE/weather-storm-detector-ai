"""AI analysis module using DeepSeek for storm detection."""

import asyncio
import aiohttp
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from models import WeatherData, StormAnalysis, AlertLevel, WeatherCondition, WeatherForecast, PredictedWeatherData
from config import Config
from chmi_warnings import ChmiWarning

logger = logging.getLogger(__name__)

class DeepSeekAnalyzer:
    """AI analyzer using DeepSeek API for storm detection."""
    
    def __init__(self, config: Config):
        """Initialize analyzer with configuration."""
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self._analysis_cache = {}  # Cache for analysis results
        self._cache_ttl = 600  # 10 minutes cache TTL
        
    async def __aenter__(self):
        """Async context manager entry."""
        headers = {
            "Authorization": f"Bearer {self.config.ai.deepseek_api_key}",
            "Content-Type": "application/json"
        }
        self.session = aiohttp.ClientSession(
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=60, connect=15)
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    def _prepare_weather_context(self, weather_data: List[WeatherData], historical_patterns: List = None, chmi_warnings: List[ChmiWarning] = None, lightning_activity: Dict[str, Any] = None) -> str:
        """Prepare weather data context for AI analysis, limiting size."""
        
        # Limit weather_data to the most recent 24 hours or a reasonable number of entries
        # Assuming weather_data is sorted by timestamp (most recent first)
        limited_weather_data = []
        if weather_data:
            # Take data from the last 24 hours, or up to 50 entries if older data is needed
            time_limit = datetime.now() - timedelta(hours=24)
            for data in weather_data:
                if data.timestamp >= time_limit:
                    limited_weather_data.append(data)
                if len(limited_weather_data) >= 50: # Cap at 50 entries to prevent excessive size
                    break
        
        context = {
            "location": {
                "city": self.config.weather.city_name,
                "region": self.config.weather.region,
                "latitude": self.config.weather.latitude,
                "longitude": self.config.weather.longitude
            },
            "current_conditions": [],
            "analysis_timestamp": datetime.now().isoformat(),
            "data_sources_count": len(limited_weather_data), # Use count of limited data
            "chmi_warnings": [],
            "historical_storm_patterns_summary": [],
            "lightning_activity": {}
        }
        
        for data in limited_weather_data:
            condition = {
                "source": data.source,
                "timestamp": data.timestamp.isoformat(),
                "temperature": data.temperature,
                "humidity": data.humidity,
                "pressure": data.pressure,
                "wind_speed": data.wind_speed,
                "wind_direction": data.wind_direction,
                "precipitation": data.precipitation,
                "precipitation_probability": data.precipitation_probability,
                "condition": data.condition.value,
                "cloud_cover": data.cloud_cover,
                "visibility": data.visibility,
                "description": data.description
            }
            context["current_conditions"].append(condition)
        
        # Add ČHMÚ warnings if available
        if chmi_warnings:
            # Limit to most recent/relevant warnings if there are many
            for warning in chmi_warnings[:5]: # Limit to top 5 warnings
                warning_data = {
                    "id": warning.identifier,
                    "event": warning.event,
                    "description": warning.detailed_text,
                    "instruction": warning.instruction,
                    "severity": warning.severity,
                    "urgency": warning.urgency,
                    "certainty": warning.certainty,
                    "color": warning.color,
                    "type": warning.warning_type,
                    "time_start": warning.time_start_iso,
                    "time_end": warning.time_end_iso,
                    "in_progress": warning.in_progress,
                    "area": warning.area_description
                }
                context["chmi_warnings"].append(warning_data)

        # Summarize historical storm patterns if available
        if historical_patterns:
            # Only include a summary of the most recent 5 patterns
            for i, pattern_data_list in enumerate(historical_patterns[:5]):
                if pattern_data_list:
                    # Take the first (most recent) data point from the pattern for summary
                    first_data_point = pattern_data_list[0]
                    summary = {
                        "pattern_id": i, # Simple ID for reference
                        "timestamp": first_data_point.get('timestamp'),
                        "condition": first_data_point.get('condition'),
                        "precipitation_probability": first_data_point.get('precipitation_probability'),
                        "summary": f"Historical pattern with {len(pattern_data_list)} data points, starting at {first_data_point.get('timestamp')}"
                    }
                    context["historical_storm_patterns_summary"].append(summary)
        
        # Add lightning activity data if available
        if lightning_activity:
            context["lightning_activity"] = {
                "recent_activity": lightning_activity,
                "summary": f"Lightning activity detected: {lightning_activity.get('total_strikes', 0)} total strikes, "
                          f"{lightning_activity.get('czech_strikes', 0)} in Czech region, "
                          f"{lightning_activity.get('nearby_strikes', 0)} within alert radius",
                "closest_distance_km": lightning_activity.get('closest_distance_km'),
                "threat_level": self._assess_lightning_threat_level(lightning_activity)
            }
        
        return json.dumps(context, indent=2)
    
    def _assess_lightning_threat_level(self, lightning_activity: Dict[str, Any]) -> str:
        """Assess lightning threat level based on activity data."""
        nearby_strikes = lightning_activity.get('nearby_strikes', 0)
        czech_strikes = lightning_activity.get('czech_strikes', 0)
        closest_distance = lightning_activity.get('closest_distance_km')
        
        # High threat: Lightning within 20km
        if closest_distance and closest_distance <= 20:
            return "HIGH"
        
        # Medium threat: Lightning within 50km or multiple Czech strikes
        if (closest_distance and closest_distance <= 50) or czech_strikes >= 3:
            return "MEDIUM"
        
        # Low threat: Some lightning activity in region
        if czech_strikes > 0 or nearby_strikes > 0:
            return "LOW"
        
        return "NONE"
    
    def _create_analysis_prompt(self, weather_context: str) -> str:
        """Create detailed prompt for storm analysis."""
        return f"""You are an expert meteorologist analyzing weather data for thunderstorm detection in Czech Republic, specifically the Brno/Reckovice area in South Moravia.

CRITICAL TASK: Analyze the provided weather data, ČHMÚ official warnings, historical storm patterns, and REAL-TIME LIGHTNING ACTIVITY to determine with HIGH ACCURACY whether a thunderstorm is approaching or occurring. This system sends email alerts to citizens, so FALSE POSITIVES must be minimized.

WEATHER DATA, OFFICIAL WARNINGS, HISTORICAL PATTERNS, AND LIGHTNING ACTIVITY:
{weather_context}

ANALYSIS REQUIREMENTS:

1. COMPREHENSIVE STORM ANALYSIS:
   - Analyze weather sensor data: pressure trends, wind patterns, humidity, precipitation probability
   - Look for classic thunderstorm indicators: rapid pressure drops, wind shifts, high humidity
   - CRITICALLY IMPORTANT: Consider official ČHMÚ warnings in the data
   - EXTREMELY IMPORTANT: Consider real-time lightning strike data from Blitzortung.org network
   - Lightning activity within 50km of Brno indicates IMMEDIATE thunderstorm threat
   - Lightning within 20km indicates SEVERE IMMEDIATE threat
   - Cross-reference sensor data with official meteorological warnings and lightning activity
   - If ČHMÚ has issued thunderstorm/rain warnings, this significantly increases confidence
   - If real-time lightning strikes are detected nearby, this is DIRECT evidence of thunderstorm activity
   - Evaluate data quality and cross-reference multiple sources
   - IMPORTANT: If current conditions match historical storm patterns, this is a strong indicator of a potential storm.

2. CONFIDENCE SCORING (0.0 to 1.0):
   - Only scores above 0.99 will trigger email alerts
   - ČHMÚ warnings and matches with historical storm patterns add significant weight to confidence scores
   - LIGHTNING ACTIVITY is CRITICAL: Real-time lightning within 50km should dramatically increase confidence (0.95+)
   - Lightning within 20km of Brno should result in MAXIMUM confidence (0.99+) as it indicates active thunderstorm
   - Consider: data consistency, meteorological indicators, official warnings, regional patterns, historical patterns, lightning activity
   - Account for data quality issues or missing information
   - If ČHMÚ has active warnings for thunderstorms/rain, confidence should be much higher
   - Lightning strikes are DIRECT evidence of thunderstorm activity - weight this heavily in analysis

3. ALERT LEVEL ASSESSMENT:
   - LOW: Minimal storm activity, light rain possible
   - MEDIUM: Moderate storm potential, some lightning possible  
   - HIGH: Strong storm likely, heavy rain, frequent lightning
   - CRITICAL: Severe thunderstorm, dangerous conditions (especially with ČHMÚ red warnings)

4. TIMING PREDICTION:
   - Estimate arrival time if storm is detected
   - Use ČHMÚ warning timing if available
   - Consider current wind patterns and movement

5. RECOMMENDATIONS:
   - Provide specific advice based on analysis
   - Include ČHMÚ instructions if available
   - Include safety recommendations if severe weather detected

CRITICAL: YOU MUST RESPOND WITH ONLY VALID JSON. NO OTHER TEXT BEFORE OR AFTER.

Your response must be exactly this JSON format (no markdown, no explanations, just pure JSON):

{{
    "storm_detected": boolean,
    "confidence_score": float (0.0-1.0),
    "alert_level": "LOW|MEDIUM|HIGH|CRITICAL",
    "predicted_arrival": "ISO timestamp or null",
    "predicted_intensity": "light|moderate|heavy|severe or null",
    "analysis_summary": "Detailed explanation of your analysis",
    "recommendations": ["recommendation1", "recommendation2", ...],
    "data_quality_score": float (0.0-1.0),
    "reasoning": "Detailed meteorological reasoning for your decision"
}}

IMPORTANT: Do not include reasoning steps, explanations, or any text outside the JSON. The JSON fields can contain your analysis. Start your response with {{ and end with }}."""

    async def analyze_weather_data(self, weather_data: List[WeatherData], historical_patterns: List = None, chmi_warnings: List[ChmiWarning] = None, lightning_activity: Dict[str, Any] = None) -> Optional[StormAnalysis]:
        """Analyze weather data using DeepSeek AI."""
        try:
            weather_context = self._prepare_weather_context(weather_data, historical_patterns, chmi_warnings, lightning_activity)
            prompt = self._create_analysis_prompt(weather_context)
            
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an expert meteorologist specializing in thunderstorm detection and analysis for the Czech Republic region. You must respond with ONLY valid JSON format, no other text, markdown, or explanations."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                "temperature": 0.1,  # Low temperature for consistent analysis
                "max_tokens": 2000
            }
            
            async with self.session.post(
                f"{self.config.ai.deepseek_api_url}/chat/completions",
                json=payload
            ) as response:
                
                if response.status == 200:
                    result = await response.json()
                    logger.debug(f"Full API response: {result}")
                    
                    if "choices" in result and len(result["choices"]) > 0:
                        message = result["choices"][0]["message"]
                        
                        # Try multiple possible fields for content
                        content_candidates = [
                            message.get("content", ""),
                            message.get("reasoning_content", ""),
                            message.get("text", ""),
                            # Sometimes the entire message is the content
                            str(message) if isinstance(message, dict) and len(str(message)) > 50 else ""
                        ]
                        
                        content = ""
                        for candidate in content_candidates:
                            if candidate and candidate.strip():
                                content = candidate.strip()
                                break
                        
                        if not content:
                            logger.error(f"Empty response content from DeepSeek API. Full response: {result}")
                            return None
                        
                        logger.debug(f"AI Response content: {content[:500]}...")
                        
                        # Parse JSON response with multiple extraction strategies
                        analysis_data = None
                        
                        # Strategy 1: Look for JSON block in markdown format
                        json_block_start = content.find('```json')
                        if json_block_start != -1:
                            json_block_start += 7  # Skip ```json
                            json_block_end = content.find('```', json_block_start)
                            if json_block_end != -1:
                                json_content = content[json_block_start:json_block_end].strip()
                                try:
                                    analysis_data = json.loads(json_content)
                                    logger.debug("Successfully parsed JSON from markdown block")
                                except json.JSONDecodeError:
                                    pass
                        
                        # Strategy 2: Extract JSON between first { and last }
                        if not analysis_data:
                            json_start = content.find('{')
                            json_end = content.rfind('}') + 1
                            
                            if json_start != -1 and json_end > json_start:
                                json_content = content[json_start:json_end]
                                try:
                                    analysis_data = json.loads(json_content)
                                    logger.debug("Successfully parsed JSON from braces extraction")
                                except json.JSONDecodeError:
                                    pass
                        
                        # Strategy 3: Try to find JSON objects line by line
                        if not analysis_data:
                            lines = content.split('\n')
                            for i, line in enumerate(lines):
                                line = line.strip()
                                if line.startswith('{'):
                                    # Try to find the matching closing brace
                                    json_content = line
                                    brace_count = 1
                                    j = i + 1
                                    while j < len(lines) and brace_count > 0:
                                        next_line = lines[j].strip()
                                        json_content += '\n' + next_line
                                        brace_count += next_line.count('{') - next_line.count('}')
                                        j += 1
                                    
                                    if brace_count == 0:
                                        try:
                                            analysis_data = json.loads(json_content)
                                            logger.debug("Successfully parsed JSON from line-by-line extraction")
                                            break
                                        except json.JSONDecodeError:
                                            continue
                        
                        if analysis_data:
                            return self._create_storm_analysis(analysis_data, weather_data)
                        else:
                            logger.error("No valid JSON found in AI response")
                            logger.error(f"Full content: {content}")
                            return None
                    else:
                        logger.error("Invalid API response structure")
                        logger.error(f"Response: {result}")
                        return None
                        
                else:
                    logger.error(f"DeepSeek API error: {response.status}")
                    error_text = await response.text()
                    logger.error(f"Error details: {error_text}")
                    return None
                    
        except asyncio.TimeoutError:
            logger.error("DeepSeek API timeout")
            return None
        except asyncio.CancelledError:
            logger.info("AI analysis cancelled during shutdown")
            return None
        except Exception as e:
            logger.error(f"DeepSeek API error: {e}")
            return None
    
    def _create_storm_analysis(self, analysis_data: Dict[str, Any], weather_data: List[WeatherData]) -> StormAnalysis:
        """Create StormAnalysis object from AI response."""
        # Map string alert level to enum
        alert_level_map = {
            "LOW": AlertLevel.LOW,
            "MEDIUM": AlertLevel.MEDIUM,
            "HIGH": AlertLevel.HIGH,
            "CRITICAL": AlertLevel.CRITICAL
        }
        
        alert_level = alert_level_map.get(
            analysis_data.get("alert_level", "LOW").upper(),
            AlertLevel.LOW
        )
        
        # Parse predicted arrival time
        predicted_arrival = None
        if analysis_data.get("predicted_arrival"):
            try:
                predicted_arrival = datetime.fromisoformat(
                    analysis_data["predicted_arrival"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                predicted_arrival = None
        
        return StormAnalysis(
            timestamp=datetime.now(),
            confidence_score=float(analysis_data.get("confidence_score", 0.0)),
            storm_detected=bool(analysis_data.get("storm_detected", False)),
            alert_level=alert_level,
            predicted_arrival=predicted_arrival,
            predicted_intensity=analysis_data.get("predicted_intensity"),
            analysis_summary=analysis_data.get("analysis_summary", ""),
            recommendations=analysis_data.get("recommendations", []),
            data_quality_score=float(analysis_data.get("data_quality_score", 0.0))
        )

class StormDetectionEngine:
    """Main engine for storm detection and analysis."""
    
    def __init__(self, config: Config):
        """Initialize detection engine."""
        self.config = config
        self.local_forecast_generator = LocalForecastGenerator(config)

    

    def _is_ai_analysis_warranted(self, weather_data: List[WeatherData], historical_patterns: List[Dict[str, Any]], chmi_warnings: List[ChmiWarning] = None) -> bool:
        """Check if conditions warrant a full AI analysis to save costs."""
        # Rule 1: Always analyze if there's an active, high-severity ČHMÚ warning
        if chmi_warnings:
            for warning in chmi_warnings:
                if warning.in_progress and warning.severity in ["Severe", "Extreme"]:
                    logger.info("AI analysis warranted due to severe ČHMÚ warning.")
                    return True

        # Rule 2: Check for local weather patterns indicative of a storm
        if weather_data:
            latest_data = weather_data[0]
            # Example thresholds (can be refined)
            if (
                latest_data.humidity > 75 and
                latest_data.wind_speed > 10 and
                latest_data.precipitation_probability > 50
            ):
                logger.info("AI analysis warranted due to local weather conditions.")
                return True

        # Rule 3: Check for matches with historical storm patterns
        match_score = self._find_historical_pattern_match(weather_data, historical_patterns)
        if match_score and match_score > 0.8:
            logger.info(f"AI analysis warranted due to historical pattern match (score: {match_score:.2f}).")
            return True

        logger.info("Conditions do not warrant a full AI analysis at this time.")
        return False

    def _find_historical_pattern_match(self, weather_data: List[WeatherData], historical_patterns: List[Dict[str, Any]]) -> Optional[float]:
        """Compare current weather data with historical storm patterns."""
        if not historical_patterns or not weather_data:
            return None

        latest_data = weather_data[0]
        best_match_score = 0.0

        for pattern_data_list in historical_patterns:
            # pattern_data_list is a list of dicts, convert to WeatherData objects
            pattern_weather_data = []
            for item in pattern_data_list:
                # Reconstruct WeatherData object from dict
                # This assumes all necessary keys are present and types match
                try:
                    wd = WeatherData(
                        timestamp=datetime.fromisoformat(item['timestamp']),
                        source=item['source'],
                        temperature=item['temperature'],
                        humidity=item['humidity'],
                        pressure=item['pressure'],
                        wind_speed=item['wind_speed'],
                        wind_direction=item['wind_direction'],
                        precipitation=item['precipitation'],
                        precipitation_probability=item['precipitation_probability'],
                        condition=WeatherCondition(item['condition']),
                        visibility=item['visibility'],
                        cloud_cover=item['cloud_cover'],
                        uv_index=item['uv_index'],
                        description=item['description'],
                        raw_data=item['raw_data']
                    )
                    pattern_weather_data.append(wd)
                except Exception as e:
                    logger.warning(f"Failed to reconstruct WeatherData from historical pattern: {e}")
                    continue

            if not pattern_weather_data:
                continue

            # Take the first (most recent) data point from the historical pattern for comparison
            pattern_latest = pattern_weather_data[0]

            score = 0.0
            # Simple comparison of key metrics
            if abs(latest_data.temperature - pattern_latest.temperature) < 2: # within 2 degrees
                score += 0.2
            if abs(latest_data.humidity - pattern_latest.humidity) < 10: # within 10%
                score += 0.2
            if abs(latest_data.pressure - pattern_latest.pressure) < 5: # within 5 hPa
                score += 0.2
            if abs(latest_data.wind_speed - pattern_latest.wind_speed) < 5: # within 5 m/s
                score += 0.2
            if latest_data.precipitation > 0 and pattern_latest.precipitation > 0: # both have precipitation
                score += 0.1
            if latest_data.precipitation_probability is not None and pattern_latest.precipitation_probability is not None and \
               latest_data.precipitation_probability > 50 and pattern_latest.precipitation_probability > 50: # both have high precip probability
                score += 0.1

            best_match_score = max(best_match_score, score)

        return best_match_score
        
    async def analyze_storm_potential(self, weather_data: List[WeatherData], chmi_warnings: List[ChmiWarning] = None, lightning_activity: Dict[str, Any] = None) -> Optional[StormAnalysis]:
        """Analyze storm potential using AI."""
        from storage import WeatherDatabase

        if not weather_data:
            logger.warning("No weather data available for analysis")
            return None

        db = WeatherDatabase(self.config)
        historical_patterns = db.get_storm_patterns()

        if not self._is_ai_analysis_warranted(weather_data, historical_patterns, chmi_warnings):
            return None
            
        async with DeepSeekAnalyzer(self.config) as analyzer:
            analysis = await analyzer.analyze_weather_data(weather_data, historical_patterns, chmi_warnings, lightning_activity)
            
        if analysis:
            logger.info(f"Storm analysis completed: confidence={analysis.confidence_score:.3f}, detected={analysis.storm_detected}")
            
            # If a storm is detected with high confidence, store the current weather data as a new pattern
            if analysis.storm_detected and analysis.confidence_score >= self.config.ai.storm_confidence_threshold:
                logger.warning(f"HIGH CONFIDENCE STORM DETECTED: {analysis.confidence_score:.3f}")
                db.store_storm_pattern("ai_detection", weather_data)
            
        # Always generate local forecast after analysis
        local_forecast = self.local_forecast_generator.generate_forecast(weather_data)
        db.store_weather_forecast(local_forecast)
        return analysis
        return analysis
    
    def should_send_alert(self, analysis: StormAnalysis) -> bool:
        """Determine if an alert should be sent based on analysis."""
        if not analysis.storm_detected:
            return False
            
        if analysis.confidence_score < self.config.ai.storm_confidence_threshold:
            logger.info(f"Storm detected but confidence too low: {analysis.confidence_score:.3f} < {self.config.ai.storm_confidence_threshold}")
            return False
            
        if analysis.alert_level in [AlertLevel.HIGH, AlertLevel.CRITICAL]:
            return True
            
        return False

class DeepSeekPredictor:
    """AI predictor using DeepSeek API for 6-hour weather forecasts."""

    def __init__(self, config: Config):
        """Initialize predictor with configuration."""
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """Async context manager entry."""
        headers = {
            "Authorization": f"Bearer {self.config.ai.deepseek_api_key}",
            "Content-Type": "application/json"
        }
        self.session = aiohttp.ClientSession(
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=60, connect=15)
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()

    def _prepare_forecast_context(self, weather_data: List[WeatherData]) -> str:
        """Prepare weather data context for AI forecast, limiting size."""
        context = {
            "location": {
                "city": self.config.weather.city_name,
                "latitude": self.config.weather.latitude,
                "longitude": self.config.weather.longitude
            },
            "current_and_recent_conditions": [],
            "analysis_timestamp": datetime.now().isoformat()
        }

        # Include up to the last 24 hours of data, or a reasonable number of entries
        limited_weather_data = sorted(weather_data, key=lambda x: x.timestamp, reverse=True)[:50]

        for data in limited_weather_data:
            condition = {
                "source": data.source,
                "timestamp": data.timestamp.isoformat(),
                "temperature": data.temperature,
                "humidity": data.humidity,
                "pressure": data.pressure,
                "wind_speed": data.wind_speed,
                "wind_direction": data.wind_direction,
                "precipitation": data.precipitation,
                "precipitation_probability": data.precipitation_probability,
                "condition": data.condition.value,
                "cloud_cover": data.cloud_cover,
                "visibility": data.visibility,
                "description": data.description
            }
            context["current_and_recent_conditions"].append(condition)

        return json.dumps(context, indent=2)

    def _create_forecast_prompt(self, weather_context: str) -> str:
        """Create detailed prompt for 6-hour weather forecast."""
        return f"""You are an expert meteorologist specializing in short-term weather forecasting for the Czech Republic, specifically the Brno/Reckovice area in South Moravia.

CRITICAL TASK: Analyze the provided current and recent weather data to predict the weather conditions for the next 6 hours, hour by hour. Focus on key meteorological parameters and analyze the trends in the data provided.

WEATHER DATA:
{weather_context}

FORECAST REQUIREMENTS:

1.  **Time Horizon**: Predict for the next 6 hours, starting from the current time.
2.  **Granularity**: Provide a prediction for each hour.
3.  **Key Parameters**: For each hour, predict:
    -   `timestamp`: ISO format for the predicted hour (e.g., current_time + 1 hour, current_time + 2 hours, etc.)
    -   `temperature`: (°C)
    -   `humidity`: (%)
    -   `pressure`: (hPa)
    -   `wind_speed`: (m/s)
    -   `wind_direction`: (degrees)
    -   `precipitation`: (mm/h)
    -   `precipitation_probability`: (%)
    -   `condition`: (e.g., clear, clouds, rain, thunderstorm, snow, drizzle, mist, fog - use the most appropriate term)
    -   `cloud_cover`: (%)
    -   `visibility`: (km)
    -   `description`: A brief textual description of the weather for that hour.
4.  **Accuracy**: Base predictions on the provided data and general meteorological principles. If data suggests a trend, continue that trend. If data is stable, predict stability.
5.  **Format**: You MUST respond with ONLY valid JSON. NO OTHER TEXT BEFORE OR AFTER. The JSON should contain a single key, "forecast", which is a list of 6 dictionaries, each representing an hourly prediction.

CRITICAL: YOU MUST RESPOND WITH ONLY VALID JSON. NO OTHER TEXT BEFORE OR AFTER.

Your response must be exactly this JSON format (no markdown, no explanations, just pure JSON):

{{
    "forecast": [
        {{
            "timestamp": "ISO timestamp for hour 1",
            "temperature": float,
            "humidity": float,
            "pressure": float,
            "wind_speed": float,
            "wind_direction": float,
            "precipitation": float,
            "precipitation_probability": float,
            "condition": "string (e.g., clear, rain)",
            "cloud_cover": float,
            "visibility": float,
            "description": "string"
        }},
        {{ /* ... similar structure for hour 2 ... */ }},
        {{ /* ... similar structure for hour 3 ... */ }},
        {{ /* ... similar structure for hour 4 ... */ }},
        {{ /* ... similar structure for hour 5 ... */ }},
        {{ /* ... similar structure for hour 6 ... */ }}
    ]
}}

IMPORTANT: Do not include reasoning steps, explanations, or any text outside the JSON. Start your response with {{ and end with }}."""

    async def generate_forecast(self, weather_data: List[WeatherData]) -> Optional[WeatherForecast]:
        """Generate 6-hour weather forecast using DeepSeek AI."""
        try:
            weather_context = self._prepare_forecast_context(weather_data)
            prompt = self._create_forecast_prompt(weather_context)

            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an expert meteorologist specializing in short-term weather forecasting. You must respond with ONLY valid JSON format, no other text, markdown, or explanations."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.5,  # Moderate temperature for balanced creativity and accuracy
                "max_tokens": 1500
            }

            async with self.session.post(
                f"{self.config.ai.deepseek_api_url}/chat/completions",
                json=payload
            ) as response:

                if response.status == 200:
                    result = await response.json()
                    logger.debug(f"Full API response for forecast: {result}")

                    if "choices" in result and len(result["choices"]) > 0:
                        content = result["choices"][0]["message"]["content"]
                        logger.debug(f"AI Forecast content: {content[:500]}...")

                        # Parse JSON response
                        forecast_data = None
                        try:
                            # Attempt to find JSON block in markdown format
                            json_block_start = content.find('```json')
                            if json_block_start != -1:
                                json_block_start += 7  # Skip ```json
                                json_block_end = content.find('```', json_block_start)
                                if json_block_end != -1:
                                    json_content = content[json_block_start:json_block_end].strip()
                                    forecast_data = json.loads(json_content)
                                    logger.debug("Successfully parsed JSON from markdown block for forecast")
                            
                            if not forecast_data:
                                # Fallback: try to extract JSON directly if not in markdown block
                                json_start = content.find('{')
                                json_end = content.rfind('}') + 1
                                if json_start != -1 and json_end > json_start:
                                    json_content = content[json_start:json_end]
                                    forecast_data = json.loads(json_content)
                                    logger.debug("Successfully parsed JSON from direct extraction for forecast")

                        except json.JSONDecodeError as e:
                            logger.error(f"JSON decoding error in forecast response: {e}")
                            logger.error(f"Problematic content: {content}")
                            return None

                        if forecast_data and "forecast" in forecast_data:
                            predicted_weather_list = []
                            for item in forecast_data["forecast"]:
                                try:
                                    predicted_weather_list.append(PredictedWeatherData(
                                        timestamp=datetime.fromisoformat(item["timestamp"]),
                                        temperature=item["temperature"],
                                        humidity=item["humidity"],
                                        pressure=item["pressure"],
                                        wind_speed=item["wind_speed"],
                                        wind_direction=item["wind_direction"],
                                        precipitation=item["precipitation"],
                                        precipitation_probability=item["precipitation_probability"],
                                        condition=WeatherCondition(item["condition"]),
                                        cloud_cover=item["cloud_cover"],
                                        visibility=item["visibility"],
                                        description=item["description"]
                                    ))
                                except Exception as e:
                                    logger.warning(f"Failed to parse predicted weather item: {item}. Error: {e}")
                                    continue
                            return WeatherForecast(timestamp=datetime.now(), forecast_data=predicted_weather_list)
                        else:
                            logger.error("Invalid forecast data structure in AI response")
                            return None
                    else:
                        logger.error("Invalid API response structure for forecast")
                        return None

                else:
                    logger.error(f"DeepSeek API error for forecast: {response.status}")
                    error_text = await response.text()
                    logger.error(f"Error details: {error_text}")
                    return None

        except asyncio.TimeoutError:
            logger.error("DeepSeek API timeout for forecast")
            return None
        except asyncio.CancelledError:
            logger.info("AI forecast generation cancelled during shutdown")
            return None
        except Exception as e:
            logger.error(f"DeepSeek API error for forecast: {e}")
            return None

        

class LocalForecastGenerator:
    """Generates a basic 6-hour weather forecast based on recent trends."""

    def __init__(self, config: Config):
        self.config = config

    def generate_forecast(self, weather_data: List[WeatherData]) -> WeatherForecast:
        """Generates a 6-hour forecast by extrapolating from the most recent data and trends."""
        if not weather_data:
            logger.warning("No weather data available for local forecast generation.")
            return WeatherForecast(timestamp=datetime.now(), forecast_data=[])

        # Sort data by timestamp (oldest first for trend analysis)
        sorted_weather_data = sorted(weather_data, key=lambda x: x.timestamp)
        
        # Take data from the last 24 hours for trend analysis
        time_limit = datetime.now() - timedelta(hours=24)
        recent_data = [d for d in sorted_weather_data if d.timestamp >= time_limit]

        if not recent_data:
            logger.warning("No recent weather data for trend analysis. Using latest data for forecast.")
            recent_data = [sorted_weather_data[-1]] # Fallback to latest if no recent

        latest_data = recent_data[-1] # Most recent data point

        forecast_data: List[PredictedWeatherData] = []
        
        # Simple linear trend calculation for temperature, humidity, pressure
        # For more robust forecasting, a proper time series model would be used
        def calculate_trend(data_points: List[float]) -> float:
            if len(data_points) < 2:
                return 0.0
            
            changes = [data_points[i] - data_points[i-1] for i in range(1, len(data_points))]
            
            if not changes:
                return 0.0
                
            # Weighted average of changes, giving more weight to more recent changes.
            weights = range(1, len(changes) + 1)
            weighted_sum = sum(c * w for c, w in zip(changes, weights))
            total_weight = sum(weights)
            
            return weighted_sum / total_weight

        # Extract values for trend analysis
        temperatures = [d.temperature for d in recent_data]
        humidities = [d.humidity for d in recent_data]
        pressures = [d.pressure for d in recent_data]

        temp_trend = calculate_trend(temperatures)
        humidity_trend = calculate_trend(humidities)
        pressure_trend = calculate_trend(pressures)

        # Average for other metrics
        avg_wind_speed = sum([d.wind_speed for d in recent_data]) / len(recent_data) if recent_data else 0.0
        avg_wind_direction = sum([d.wind_direction for d in recent_data]) / len(recent_data) if recent_data else 0.0
        avg_precipitation = sum([d.precipitation for d in recent_data]) / len(recent_data) if recent_data else 0.0
        avg_precipitation_probability = sum([d.precipitation_probability for d in recent_data if d.precipitation_probability is not None]) / len([d for d in recent_data if d.precipitation_probability is not None]) if [d for d in recent_data if d.precipitation_probability is not None] else 0.0
        avg_cloud_cover = sum([d.cloud_cover for d in recent_data]) / len(recent_data) if recent_data else 0.0
        avg_visibility = sum([d.visibility for d in recent_data if d.visibility is not None]) / len([d for d in recent_data if d.visibility is not None]) if [d for d in recent_data if d.visibility is not None] else 10.0
        
        # Determine most frequent condition
        condition_counts = {}
        for d in recent_data:
            condition_counts[d.condition] = condition_counts.get(d.condition, 0) + 1
        most_frequent_condition = max(condition_counts, key=condition_counts.get) if condition_counts else WeatherCondition.CLEAR

        for i in range(1, 7):  # For the next 6 hours
            predicted_timestamp = datetime.now() + timedelta(hours=i)
            
            # Apply trend for temperature, humidity, pressure
            predicted_temperature = latest_data.temperature + (temp_trend * i)
            predicted_humidity = latest_data.humidity + (humidity_trend * i)
            predicted_pressure = latest_data.pressure + (pressure_trend * i)

            # Clamp values to reasonable ranges
            predicted_humidity = max(0.0, min(100.0, predicted_humidity))
            predicted_pressure = max(900.0, min(1100.0, predicted_pressure)) # Typical pressure range

            # For other metrics, use the average from recent data
            forecast_data.append(PredictedWeatherData(
                timestamp=predicted_timestamp,
                temperature=predicted_temperature,
                humidity=predicted_humidity,
                pressure=predicted_pressure,
                wind_speed=avg_wind_speed,
                wind_direction=avg_wind_direction,
                precipitation=avg_precipitation,
                precipitation_probability=avg_precipitation_probability,
                condition=most_frequent_condition,
                cloud_cover=avg_cloud_cover,
                visibility=avg_visibility,
                description=f"Forecast for hour {i}" # Generic description
            ))
        return WeatherForecast(timestamp=datetime.now(), forecast_data=forecast_data)

class DeepSeekChatAnalyzer:
    """AI chat analyzer using DeepSeek for daily summaries and general analysis."""
    
    def __init__(self, config: Config):
        """Initialize chat analyzer with configuration."""
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        """Async context manager entry."""
        headers = {
            "Authorization": f"Bearer {self.config.ai.deepseek_api_key}",
            "Content-Type": "application/json"
        }
        self.session = aiohttp.ClientSession(
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=60, connect=30)
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def generate_daily_summary(self, weather_data: List[WeatherData], chmi_warnings: List[ChmiWarning] = None) -> str:
        """Generate AI-powered daily weather summary in Czech."""
        try:
            # Prepare context
            current_weather = weather_data[0] if weather_data else None
            
            context = f"""AKTUÁLNÍ POČASÍ PRO {self.config.weather.city_name.upper()}:
Datum: {datetime.now().strftime('%d.%m.%Y')}
Čas: {datetime.now().strftime('%H:%M')}

"""
            
            if current_weather:
                context += f"""METEOROLOGICKÉ ÚDAJE:
- Teplota: {current_weather.temperature:.1f}°C
- Vlhkost: {current_weather.humidity:.0f}%
- Tlak: {current_weather.pressure:.0f} hPa
- Vítr: {current_weather.wind_speed:.1f} m/s ze směru {current_weather.wind_direction}°
- Oblačnost: {current_weather.cloud_cover:.0f}%
- Srážky: {current_weather.precipitation:.1f} mm
- Viditelnost: {current_weather.visibility:.1f} km
- Popis: {current_weather.description}

"""
            
            if chmi_warnings:
                context += "OFICIÁLNÍ VAROVÁNÍ ČHMÚ:\n"
                for warning in chmi_warnings:
                    context += f"- {warning.event} ({warning.color}) - {warning.time_start_text}\n"
                context += "\n"
            else:
                context += "OFICIÁLNÍ VAROVÁNÍ ČHMÚ: Žádná aktuální varování\n\n"
            
            prompt = f"""{context}
Úkol: Vytvoř krátký, přehledný souhrn počasí pro dnešní den v češtině. 

Požadavky:
1. Maximálně 150 slov
2. Zaměř se na praktické informace pro občany
3. Uveď aktuální podmínky a očekávaný vývoj
4. Pokud jsou varování ČHMÚ, zdůrazni je
5. Doporuč vhodné oblečení/aktivity
6. Použij přirozený český jazyk

Odpověz pouze se shrnutím, bez dalších komentářů."""

            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {
                        "role": "system",
                        "content": "Jsi meteorolog specializující se na předpověď počasí pro České republiky. Tvoje shrnutí jsou přesná, praktická a v češtině."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                "temperature": 0.7,  # More creative for summaries
                "max_tokens": 300
            }
            
            async with self.session.post(
                f"{self.config.ai.deepseek_api_url}/chat/completions",
                json=payload
            ) as response:
                
                if response.status == 200:
                    result = await response.json()
                    
                    if "choices" in result and len(result["choices"]) > 0:
                        content = result["choices"][0]["message"]["content"]
                        logger.info("Daily summary generated successfully")
                        return content.strip()
                else:
                    logger.error(f"DeepSeek API error: {response.status}")
                    return "Automatické shrnutí počasí dnes není k dispozici. Sledujte aktuální předpověď na ČHMÚ."
                    
        except Exception as e:
            logger.error(f"Error generating daily summary: {e}")
            return "Automatické shrnutí počasí dnes není k dispozici. Sledujte aktuální předpověď na ČHMÚ."