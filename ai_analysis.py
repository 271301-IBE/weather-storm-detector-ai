"""AI analysis module using DeepSeek for storm detection."""

import asyncio
import aiohttp
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from models import WeatherData, StormAnalysis, AlertLevel
from config import Config
from chmi_warnings import ChmiWarning

logger = logging.getLogger(__name__)

class DeepSeekAnalyzer:
    """AI analyzer using DeepSeek API for storm detection."""
    
    def __init__(self, config: Config):
        """Initialize analyzer with configuration."""
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
            timeout=aiohttp.ClientTimeout(total=120, connect=30)
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    def _prepare_weather_context(self, weather_data: List[WeatherData], historical_data: List = None, chmi_warnings: List[ChmiWarning] = None) -> str:
        """Prepare weather data context for AI analysis."""
        context = {
            "location": {
                "city": self.config.weather.city_name,
                "region": self.config.weather.region,
                "latitude": self.config.weather.latitude,
                "longitude": self.config.weather.longitude
            },
            "current_conditions": [],
            "analysis_timestamp": datetime.now().isoformat(),
            "data_sources": len(weather_data),
            "chmi_warnings": []
        }
        
        for data in weather_data:
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
            for warning in chmi_warnings:
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
        
        return json.dumps(context, indent=2)
    
    def _create_analysis_prompt(self, weather_context: str) -> str:
        """Create detailed prompt for storm analysis."""
        return f"""You are an expert meteorologist analyzing weather data for thunderstorm detection in Czech Republic, specifically the Brno/Reckovice area in South Moravia.

CRITICAL TASK: Analyze the provided weather data and ČHMÚ official warnings to determine with HIGH ACCURACY whether a thunderstorm is approaching or occurring. This system sends email alerts to citizens, so FALSE POSITIVES must be minimized.

WEATHER DATA AND OFFICIAL WARNINGS:
{weather_context}

ANALYSIS REQUIREMENTS:

1. COMPREHENSIVE STORM ANALYSIS:
   - Analyze weather sensor data: pressure trends, wind patterns, humidity, precipitation probability
   - Look for classic thunderstorm indicators: rapid pressure drops, wind shifts, high humidity
   - CRITICALLY IMPORTANT: Consider official ČHMÚ warnings in the data
   - Cross-reference sensor data with official meteorological warnings
   - If ČHMÚ has issued thunderstorm/rain warnings, this significantly increases confidence
   - Evaluate data quality and cross-reference multiple sources

2. CONFIDENCE SCORING (0.0 to 1.0):
   - Only scores above 0.99 will trigger email alerts
   - ČHMÚ warnings add significant weight to confidence scores
   - Consider: data consistency, meteorological indicators, official warnings, regional patterns
   - Account for data quality issues or missing information
   - If ČHMÚ has active warnings for thunderstorms/rain, confidence should be much higher

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

RESPOND WITH VALID JSON ONLY:
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

REMEMBER: High accuracy is critical. Only indicate storm detection with high confidence when meteorological evidence strongly supports it."""

    async def analyze_weather_data(self, weather_data: List[WeatherData], historical_data: List = None, chmi_warnings: List[ChmiWarning] = None) -> Optional[StormAnalysis]:
        """Analyze weather data using DeepSeek AI."""
        try:
            weather_context = self._prepare_weather_context(weather_data, historical_data, chmi_warnings)
            prompt = self._create_analysis_prompt(weather_context)
            
            payload = {
                "model": "deepseek-reasoner",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an expert meteorologist specializing in thunderstorm detection and analysis for the Czech Republic region."
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
                        # DeepSeek Reasoner might put the actual content in reasoning_content
                        content = message.get("content", "") or message.get("reasoning_content", "")
                        
                        if not content.strip():
                            logger.error("Empty response content from DeepSeek API")
                            return None
                        
                        logger.debug(f"AI Response content: {content[:500]}...")
                        
                        # Parse JSON response
                        try:
                            # Try to extract JSON from the response (handle extra content after JSON)
                            json_start = content.find('{')
                            json_end = content.rfind('}') + 1
                            
                            if json_start != -1 and json_end > json_start:
                                json_content = content[json_start:json_end]
                                analysis_data = json.loads(json_content)
                                return self._create_storm_analysis(analysis_data, weather_data)
                            else:
                                logger.error("No valid JSON found in AI response")
                                return None
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse AI response as JSON: {e}")
                            logger.error(f"AI Response: {content}")
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
        
    async def analyze_storm_potential(self, weather_data: List[WeatherData], historical_data: List = None, chmi_warnings: List[ChmiWarning] = None) -> Optional[StormAnalysis]:
        """Analyze storm potential using AI."""
        if not weather_data:
            logger.warning("No weather data available for analysis")
            return None
            
        async with DeepSeekAnalyzer(self.config) as analyzer:
            analysis = await analyzer.analyze_weather_data(weather_data, historical_data, chmi_warnings)
            
        if analysis:
            logger.info(f"Storm analysis completed: confidence={analysis.confidence_score:.3f}, detected={analysis.storm_detected}")
            
            # Additional validation logic
            if analysis.storm_detected and analysis.confidence_score >= self.config.ai.storm_confidence_threshold:
                logger.warning(f"HIGH CONFIDENCE STORM DETECTED: {analysis.confidence_score:.3f}")
            
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