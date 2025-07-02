#!/usr/bin/env python3
"""
Test script for the enhanced weather forecasting system.
Validates the new advanced algorithms and UI integration.
"""

import sys
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timedelta

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from config import load_config
from storage import WeatherDatabase
from models import WeatherData, WeatherCondition
from advanced_forecast import AdvancedForecastGenerator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EnhancedForecastTester:
    """Test suite for enhanced forecasting functionality."""
    
    def __init__(self):
        self.config = load_config()
        self.db = WeatherDatabase(self.config)
        self.test_results = {}
    
    def generate_mock_weather_data(self, hours: int = 24) -> list:
        """Generate mock weather data for testing."""
        mock_data = []
        base_time = datetime.now() - timedelta(hours=hours)
        
        for i in range(hours * 6):  # Every 10 minutes
            timestamp = base_time + timedelta(minutes=i * 10)
            
            # Simulate realistic weather patterns
            temp_cycle = 15 + 10 * math.sin((i / 144) * 2 * math.pi)  # Daily temperature cycle
            humidity = 60 + 20 * math.sin((i / 72) * math.pi + 1)    # Humidity variation
            pressure = 1013 + 5 * math.sin((i / 200) * math.pi)      # Pressure variation
            
            mock_data.append(WeatherData(
                timestamp=timestamp,
                source="mock_api",
                temperature=temp_cycle + (i % 3 - 1) * 2,  # Add some noise
                humidity=max(30, min(95, humidity + (i % 5 - 2) * 3)),
                pressure=pressure + (i % 4 - 1.5) * 2,
                wind_speed=5 + (i % 7) * 0.5,
                wind_direction=(i * 15) % 360,
                precipitation=max(0, (i % 20 - 18) * 0.5),  # Occasional rain
                precipitation_probability=max(0, min(100, 20 + (i % 15 - 7) * 10)),
                condition=WeatherCondition.CLOUDS if i % 8 < 3 else WeatherCondition.CLEAR,
                visibility=10.0,
                cloud_cover=30 + (i % 10) * 7,
                uv_index=5.0,
                description="Mock weather data for testing",
                raw_data={"mock": True}
            ))
        
        return mock_data
    
    async def test_physics_forecast(self, weather_data: list) -> dict:
        """Test the physics-based forecasting."""
        logger.info("Testing physics-based forecasting...")
        
        try:
            async with AdvancedForecastGenerator(self.config) as generator:
                forecast = await generator.generate_physics_forecast(weather_data)
                
                if forecast and forecast.forecast_data:
                    result = {
                        'success': True,
                        'forecast_hours': len(forecast.forecast_data),
                        'method': forecast.primary_method.value,
                        'confidence': forecast.method_confidences.get('physics', 0),
                        'sample_temp': forecast.forecast_data[0].temperature if forecast.forecast_data else None,
                        'metadata_quality': forecast.forecast_data[0].metadata.data_quality if forecast.forecast_data else None
                    }
                    logger.info(f"Physics forecast: {result}")
                    return result
                else:
                    return {'success': False, 'error': 'No forecast generated'}
                    
        except Exception as e:
            logger.error(f"Physics forecast test failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def test_ai_forecast(self, weather_data: list) -> dict:
        """Test the AI-based forecasting."""
        logger.info("Testing AI-based forecasting...")
        
        try:
            async with AdvancedForecastGenerator(self.config) as generator:
                # Note: This will actually call DeepSeek API
                forecast = await generator.generate_ai_forecast(weather_data)
                
                if forecast and forecast.forecast_data:
                    result = {
                        'success': True,
                        'forecast_hours': len(forecast.forecast_data),
                        'method': forecast.primary_method.value,
                        'confidence': forecast.method_confidences.get('ai_deepseek', 0),
                        'sample_temp': forecast.forecast_data[0].temperature if forecast.forecast_data else None,
                        'api_call': True
                    }
                    logger.info(f"AI forecast: {result}")
                    return result
                else:
                    return {'success': False, 'error': 'No AI forecast generated (API may be down)'}
                    
        except Exception as e:
            logger.error(f"AI forecast test failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def test_ensemble_forecast(self, weather_data: list) -> dict:
        """Test the ensemble forecasting."""
        logger.info("Testing ensemble forecasting...")
        
        try:
            async with AdvancedForecastGenerator(self.config) as generator:
                forecast = await generator.generate_ensemble_forecast(weather_data)
                
                if forecast and forecast.forecast_data:
                    result = {
                        'success': True,
                        'forecast_hours': len(forecast.forecast_data),
                        'method': forecast.primary_method.value,
                        'ensemble_weights': forecast.ensemble_weight,
                        'method_confidences': forecast.method_confidences,
                        'data_sources': forecast.data_sources,
                        'sample_temp': forecast.forecast_data[0].temperature if forecast.forecast_data else None
                    }
                    logger.info(f"Ensemble forecast: {result}")
                    return result
                else:
                    return {'success': False, 'error': 'No ensemble forecast generated'}
                    
        except Exception as e:
            logger.error(f"Ensemble forecast test failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def test_database_integration(self) -> dict:
        """Test database storage and retrieval of enhanced forecasts."""
        logger.info("Testing database integration...")
        
        try:
            # Test getting recent weather data
            recent_data = self.db.get_recent_weather_data(hours=24)
            
            # Test creating enhanced forecasts table
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS enhanced_forecasts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        method TEXT NOT NULL,
                        forecast_data_json TEXT NOT NULL,
                        confidence_data TEXT,
                        metadata TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
            
            result = {
                'success': True,
                'recent_data_count': len(recent_data),
                'table_created': True,
                'data_sources': list(set([d.source for d in recent_data])) if recent_data else []
            }
            logger.info(f"Database integration: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Database integration test failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def test_api_endpoints(self) -> dict:
        """Test new API endpoint functionality (simulation)."""
        logger.info("Testing API endpoint logic...")
        
        try:
            # Simulate the logic that would be in the API endpoints
            from web_app import app
            
            # Test that routes exist
            routes = [rule.rule for rule in app.url_map.iter_rules()]
            enhanced_routes = [
                '/api/enhanced_forecast',
                '/api/forecast_accuracy', 
                '/api/forecast_comparison'
            ]
            
            missing_routes = [route for route in enhanced_routes if route not in routes]
            
            result = {
                'success': len(missing_routes) == 0,
                'all_routes_exist': len(missing_routes) == 0,
                'missing_routes': missing_routes,
                'total_routes': len(routes)
            }
            logger.info(f"API endpoints: {result}")
            return result
            
        except Exception as e:
            logger.error(f"API endpoint test failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def run_all_tests(self) -> dict:
        """Run comprehensive test suite."""
        logger.info("🧪 Starting Enhanced Forecast Test Suite")
        logger.info("=" * 60)
        
        # Generate mock data for testing
        import math  # Import needed for mock data generation
        mock_data = self.generate_mock_weather_data(24)
        logger.info(f"Generated {len(mock_data)} mock weather data points")
        
        # Run all tests
        tests = {
            'database_integration': self.test_database_integration(),
            'api_endpoints': self.test_api_endpoints(),
            'physics_forecast': await self.test_physics_forecast(mock_data),
            # Skip AI test by default to avoid API costs
            # 'ai_forecast': await self.test_ai_forecast(mock_data),
            'ensemble_forecast': await self.test_ensemble_forecast(mock_data)
        }
        
        # Summarize results
        total_tests = len(tests)
        passed_tests = sum(1 for result in tests.values() if result.get('success', False))
        
        summary = {
            'total_tests': total_tests,
            'passed_tests': passed_tests,
            'failed_tests': total_tests - passed_tests,
            'success_rate': (passed_tests / total_tests) * 100 if total_tests > 0 else 0,
            'test_results': tests
        }
        
        logger.info("=" * 60)
        logger.info(f"📊 Test Summary: {passed_tests}/{total_tests} tests passed ({summary['success_rate']:.1f}%)")
        
        for test_name, result in tests.items():
            status = "✅ PASS" if result.get('success') else "❌ FAIL"
            error = f" - {result.get('error', '')}" if not result.get('success') else ""
            logger.info(f"  {status} {test_name}{error}")
        
        return summary

def main():
    """Run the test suite."""
    print("🌩️ Enhanced Weather Forecast Testing")
    print("=" * 50)
    
    try:
        tester = EnhancedForecastTester()
        results = asyncio.run(tester.run_all_tests())
        
        print("\n📋 Detailed Results:")
        for test_name, result in results['test_results'].items():
            print(f"\n{test_name.upper()}:")
            for key, value in result.items():
                if key != 'success':
                    print(f"  {key}: {value}")
        
        if results['success_rate'] >= 80:
            print("\n🎉 Enhanced forecasting system is ready for deployment!")
        else:
            print("\n⚠️  Some tests failed. Please review and fix issues before deployment.")
            
        return 0 if results['success_rate'] >= 80 else 1
        
    except Exception as e:
        print(f"\n❌ Test suite failed with error: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)