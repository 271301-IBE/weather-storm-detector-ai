#!/usr/bin/env python3
"""
Test script to verify forecast generation works properly.
"""

import asyncio
import logging
from datetime import datetime
from config import load_config
from storage import WeatherDatabase
from advanced_forecast import AdvancedForecastGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_forecast_generation():
    """Test forecast generation and storage."""
    logger.info("Testing forecast generation...")
    
    config = load_config()
    db = WeatherDatabase(config)
    
    # Get recent weather data
    weather_data = db.get_recent_weather_data(hours=24)
    logger.info(f"Found {len(weather_data)} weather records")
    
    async with AdvancedForecastGenerator(config) as generator:
        # Test physics forecast
        logger.info("Generating physics forecast...")
        physics_forecast = await generator.generate_physics_forecast(weather_data)
        if physics_forecast:
            logger.info(f"Physics forecast: {len(physics_forecast.forecast_data)} hours")
            logger.info(f"First hour temp: {physics_forecast.forecast_data[0].temperature:.1f}°C")
            # Store it
            db.store_enhanced_forecast(physics_forecast, 'physics')
            logger.info("Physics forecast stored")
        else:
            logger.error("Physics forecast failed")
        
        # Test AI forecast (if API key available)
        if config.ai.deepseek_api_key:
            logger.info("Generating AI forecast...")
            ai_forecast = await generator.generate_ai_forecast(weather_data)
            if ai_forecast:
                logger.info(f"AI forecast: {len(ai_forecast.forecast_data)} hours")
                logger.info(f"First hour temp: {ai_forecast.forecast_data[0].temperature:.1f}°C")
                # Store it
                db.store_enhanced_forecast(ai_forecast, 'ai')
                logger.info("AI forecast stored")
            else:
                logger.warning("AI forecast failed (may be normal if no API key)")
        else:
            logger.info("Skipping AI forecast (no API key)")
        
        # Test ensemble forecast
        logger.info("Generating ensemble forecast...")
        ensemble_forecast = await generator.generate_ensemble_forecast(weather_data)
        if ensemble_forecast:
            logger.info(f"Ensemble forecast: {len(ensemble_forecast.forecast_data)} hours")
            logger.info(f"First hour temp: {ensemble_forecast.forecast_data[0].temperature:.1f}°C")
            # Store it
            db.store_enhanced_forecast(ensemble_forecast, 'ensemble')
            logger.info("Ensemble forecast stored")
        else:
            logger.error("Ensemble forecast failed")
    
    # Test retrieval
    logger.info("Testing forecast retrieval...")
    retrieved_physics = db.get_latest_forecast_by_method('physics')
    retrieved_ai = db.get_latest_forecast_by_method('ai')
    retrieved_ensemble = db.get_latest_forecast_by_method('ensemble')
    
    logger.info(f"Retrieved physics forecast: {'OK' if retrieved_physics else 'FAILED'}")
    logger.info(f"Retrieved AI forecast: {'OK' if retrieved_ai else 'FAILED'}")
    logger.info(f"Retrieved ensemble forecast: {'OK' if retrieved_ensemble else 'FAILED'}")
    
    if retrieved_physics:
        logger.info(f"Physics forecast has {len(retrieved_physics.forecast_data)} hours")
        if retrieved_physics.forecast_data:
            temp = retrieved_physics.forecast_data[0].temperature
            logger.info(f"Physics first hour temp: {temp:.1f}°C")
            if temp < -40 or temp > 50:
                logger.error("Physics forecast has unrealistic temperature!")
            else:
                logger.info("Physics forecast temperature looks realistic")
    
    logger.info("Test completed!")

if __name__ == "__main__":
    asyncio.run(test_forecast_generation())