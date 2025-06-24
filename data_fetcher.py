"""Weather data fetching module."""

import asyncio
import aiohttp
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
import time

from models import WeatherData, WeatherCondition
from config import Config

logger = logging.getLogger(__name__)

class WeatherDataFetcher:
    """Fetches weather data from multiple APIs."""
    
    def __init__(self, config: Config):
        """Initialize fetcher with configuration."""
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(limit=10)
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def fetch_openweather_data(self) -> Optional[WeatherData]:
        """Fetch data from OpenWeather API."""
        try:
            url = "https://api.openweathermap.org/data/2.5/weather"
            params = {
                "lat": self.config.weather.latitude,
                "lon": self.config.weather.longitude,
                "appid": self.config.weather.openweather_api_key,
                "units": "metric"
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_openweather_data(data)
                else:
                    logger.error(f"OpenWeather API error: {response.status}")
                    return None
                    
        except asyncio.TimeoutError:
            logger.error("OpenWeather API timeout")
            return None
        except Exception as e:
            logger.error(f"OpenWeather API error: {e}")
            return None
    
    async def fetch_visual_crossing_data(self) -> Optional[WeatherData]:
        """Fetch data from Visual Crossing API."""
        try:
            location = f"{self.config.weather.latitude},{self.config.weather.longitude}"
            url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{location}"
            
            params = {
                "key": self.config.weather.visual_crossing_api_key,
                "include": "current",
                "unitGroup": "metric"
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_visual_crossing_data(data)
                else:
                    logger.error(f"Visual Crossing API error: {response.status}")
                    return None
                    
        except asyncio.TimeoutError:
            logger.error("Visual Crossing API timeout")
            return None
        except Exception as e:
            logger.error(f"Visual Crossing API error: {e}")
            return None
    
    def _parse_openweather_data(self, data: Dict[str, Any]) -> WeatherData:
        """Parse OpenWeather API response."""
        main = data.get("main", {})
        weather = data.get("weather", [{}])[0]
        wind = data.get("wind", {})
        clouds = data.get("clouds", {})
        
        # Map OpenWeather condition to our enum
        condition_map = {
            "Clear": WeatherCondition.CLEAR,
            "Clouds": WeatherCondition.CLOUDS,
            "Rain": WeatherCondition.RAIN,
            "Thunderstorm": WeatherCondition.THUNDERSTORM,
            "Snow": WeatherCondition.SNOW,
            "Drizzle": WeatherCondition.DRIZZLE,
            "Mist": WeatherCondition.MIST,
            "Fog": WeatherCondition.FOG,
        }
        
        condition = condition_map.get(weather.get("main"), WeatherCondition.CLEAR)
        
        return WeatherData(
            timestamp=datetime.now(),
            source="openweather",
            temperature=main.get("temp", 0.0),
            humidity=main.get("humidity", 0.0),
            pressure=main.get("pressure", 0.0),
            wind_speed=wind.get("speed", 0.0),
            wind_direction=wind.get("deg", 0.0),
            precipitation=data.get("rain", {}).get("1h", 0.0),
            precipitation_probability=0.0,  # Not available in current weather
            condition=condition,
            visibility=data.get("visibility", 10000) / 1000,  # Convert to km
            cloud_cover=clouds.get("all", 0.0),
            uv_index=None,  # Not available in basic plan
            description=weather.get("description", ""),
            raw_data=data
        )
    
    def _parse_visual_crossing_data(self, data: Dict[str, Any]) -> WeatherData:
        """Parse Visual Crossing API response."""
        current = data.get("currentConditions", {})
        
        # Map Visual Crossing condition to our enum
        conditions_str = current.get("conditions", "").lower()
        if "thunderstorm" in conditions_str or "storm" in conditions_str:
            condition = WeatherCondition.THUNDERSTORM
        elif "rain" in conditions_str:
            condition = WeatherCondition.RAIN
        elif "drizzle" in conditions_str:
            condition = WeatherCondition.DRIZZLE
        elif "snow" in conditions_str:
            condition = WeatherCondition.SNOW
        elif "cloud" in conditions_str:
            condition = WeatherCondition.CLOUDS
        elif "fog" in conditions_str:
            condition = WeatherCondition.FOG
        elif "mist" in conditions_str:
            condition = WeatherCondition.MIST
        else:
            condition = WeatherCondition.CLEAR
        
        return WeatherData(
            timestamp=datetime.now(),
            source="visual_crossing",
            temperature=current.get("temp", 0.0),
            humidity=current.get("humidity", 0.0),
            pressure=current.get("pressure", 0.0),
            wind_speed=current.get("windspeed", 0.0),
            wind_direction=current.get("winddir", 0.0),
            precipitation=current.get("precip", 0.0),
            precipitation_probability=current.get("precipprob", 0.0),
            condition=condition,
            visibility=current.get("visibility", 10.0),
            cloud_cover=current.get("cloudcover", 0.0),
            uv_index=current.get("uvindex"),
            description=current.get("conditions", ""),
            raw_data=data
        )
    
    async def fetch_all_data(self) -> List[WeatherData]:
        """Fetch data from all available APIs concurrently."""
        tasks = [
            self.fetch_openweather_data(),
            self.fetch_visual_crossing_data()
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        weather_data = []
        for result in results:
            if isinstance(result, WeatherData):
                weather_data.append(result)
            elif isinstance(result, Exception):
                logger.error(f"API fetch error: {result}")
        
        logger.info(f"Successfully fetched data from {len(weather_data)} APIs")
        return weather_data

class WeatherDataCollector:
    """Main collector that orchestrates data fetching."""
    
    def __init__(self, config: Config):
        """Initialize collector."""
        self.config = config
        self.last_fetch_time = None
        
    async def collect_weather_data(self) -> List[WeatherData]:
        """Collect weather data from all sources."""
        start_time = time.time()
        
        async with WeatherDataFetcher(self.config) as fetcher:
            weather_data = await fetcher.fetch_all_data()
        
        fetch_duration = time.time() - start_time
        logger.info(f"Data collection completed in {fetch_duration:.2f} seconds")
        
        self.last_fetch_time = datetime.now()
        return weather_data
    
    def get_data_quality_score(self, weather_data: List[WeatherData]) -> float:
        """Calculate data quality score based on available data."""
        if not weather_data:
            return 0.0
            
        total_score = 0.0
        for data in weather_data:
            score = 1.0
            
            # Check for missing critical data
            if data.temperature == 0.0:
                score -= 0.2
            if data.humidity == 0.0:
                score -= 0.2
            if data.pressure == 0.0:
                score -= 0.2
            if data.wind_speed == 0.0:
                score -= 0.1
            if not data.description:
                score -= 0.1
                
            total_score += max(0.0, score)
        
        return total_score / len(weather_data)